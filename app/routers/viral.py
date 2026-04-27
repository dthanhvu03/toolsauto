from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import time
from app.database.core import get_db
from app.main_templates import templates
from app.services.viral_service import ViralService

router = APIRouter(prefix="/viral", tags=["viral"])


def _render_viral_tbody(request: Request, db: Session, scan_message: str | None = None) -> str:
    data = ViralService.get_viral_table_data(db)
    now = int(time.time())
    parts = []
    if scan_message:
        parts.append(
            f'<tr class="bg-green-50 border-b">'
            f'<td colspan="7" class="p-3 text-sm text-green-800">{scan_message}</td></tr>'
        )
    if data["total_count"] > 0:
        showing = len(data["materials"])
        parts.append(
            f'<tr class="bg-gray-50 border-b"><td colspan="7" class="p-2 text-xs text-gray-500">'
            f'Hiển thị {showing} / {data["total_count"]} video (sắp theo views giảm dần, tối đa {ViralService.VIRAL_TABLE_LIMIT})'
            f'</td></tr>'
        )
    for item in data["materials"]:
        acc_name = data["accounts"].get(item.scraped_by_account_id, "Unknown")
        parts.append(
            templates.get_template("fragments/viral_row.html").render(
                {"request": request, "item": item, "account_name": acc_name, "now": now}
            )
        )
    if not parts:
        parts.append(
            '<tr><td colspan="7" class="p-4 text-center text-sm text-gray-500">Chưa có video viral nào.</td></tr>'
        )
    return "".join(parts)


@router.get("/table", response_class=HTMLResponse)
def get_viral_table(request: Request, db: Session = Depends(get_db)):
    return HTMLResponse(content=_render_viral_tbody(request, db))


@router.post("/force-scan", response_class=HTMLResponse)
def force_scan(request: Request, db: Session = Depends(get_db)):
    _, _, msg = ViralService.force_scan(db)
    return HTMLResponse(content=_render_viral_tbody(request, db, scan_message=msg))


def _render_viral_settings(viral_min_views: int, viral_max_videos: int, saved: bool = False) -> str:
    msg = ' <span class="text-green-600 text-xs">Đã lưu.</span>' if saved else ''
    return (
        f'<div id="viral-settings" class="flex items-center gap-3 flex-wrap">'
        f'<label class="text-sm text-gray-600 flex items-center gap-2">'
        f'Ngưỡng view tối thiểu: '
        f'<input type="number" name="viral_min_views" value="{viral_min_views}" min="500" max="10000000" step="500" '
        f'class="w-24 border border-gray-300 rounded px-2 py-1 text-sm"> '
        f'<span class="text-gray-400 text-xs">views</span></label>'
        f'<label class="text-sm text-gray-600 flex items-center gap-2">'
        f'Số video tối đa mỗi kênh: '
        f'<input type="number" name="viral_max_videos_per_channel" value="{viral_max_videos}" min="0" max="500" '
        f'class="w-20 border border-gray-300 rounded px-2 py-1 text-sm" title="0 = lấy tối đa (cap 500)">'
        f'</label>'
        f'<button type="button" hx-post="/viral/settings" hx-include="[name=\'viral_min_views\'], [name=\'viral_max_videos_per_channel\']" '
        f'hx-target="#viral-settings" hx-swap="outerHTML" '
        f'class="text-sm bg-gray-600 hover:bg-gray-700 text-white px-3 py-1 rounded">Lưu</button>'
        f'{msg}</div>'
    )


@router.post("/settings", response_class=HTMLResponse)
def save_viral_settings(viral_min_views: int = Form(10000), viral_max_videos_per_channel: int = Form(50), db: Session = Depends(get_db)):
    res = ViralService.save_settings(db, viral_min_views, viral_max_videos_per_channel)
    return HTMLResponse(content=_render_viral_settings(res["min_views"], res["max_videos"], saved=True))


@router.post("/{material_id}/delete", response_class=HTMLResponse)
def delete_material(material_id: int, db: Session = Depends(get_db)):
    ViralService.delete_material(db, material_id)
    return HTMLResponse(content="")
