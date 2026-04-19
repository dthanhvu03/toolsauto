from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import time
from app.database.core import get_db
from app.database.models import ViralMaterial, Account, SystemState
from app.main_templates import templates
from app.services.worker import WorkerService
from app.services.viral_scan import run_tiktok_competitor_scan, get_default_min_views

router = APIRouter(prefix="/viral", tags=["viral"])


# Số dòng tối đa hiển thị trên bảng Viral (không lọc status — hiển thị NEW + DRAFTED + FAILED)
VIRAL_TABLE_LIMIT = 500


def _render_viral_tbody(request: Request, db: Session, scan_message: str | None = None) -> str:
    # Không lọc status — lấy tất cả, sắp views giảm dần, giới hạn 500
    materials = (
        db.query(ViralMaterial)
        .order_by(ViralMaterial.views.desc())
        .limit(VIRAL_TABLE_LIMIT)
        .all()
    )
    total_count = db.query(ViralMaterial).count()
    accounts = {acc.id: acc.name for acc in db.query(Account).all()}
    now = int(time.time())
    parts = []
    if scan_message:
        parts.append(
            f'<tr class="bg-green-50 border-b">'
            f'<td colspan="7" class="p-3 text-sm text-green-800">{scan_message}</td></tr>'
        )
    # Dòng thông tin: đang hiển thị X / tổng Y
    if total_count > 0:
        showing = min(len(materials), VIRAL_TABLE_LIMIT)
        parts.append(
            f'<tr class="bg-gray-50 border-b"><td colspan="7" class="p-2 text-xs text-gray-500">'
            f'Hiển thị {showing} / {total_count} video (sắp theo views giảm dần, tối đa {VIRAL_TABLE_LIMIT})'
            f'</td></tr>'
        )
    for item in materials:
        acc_name = accounts.get(item.scraped_by_account_id, "Unknown")
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
    """Quét thủ công kênh TikTok đối thủ → thêm video mới vào bảng (status Mới quét)."""
    try:
        total_found, num_channels = run_tiktok_competitor_scan(db)
        if num_channels == 0:
            msg = "Không có kênh TikTok đối thủ nào trong cấu hình account."
        elif total_found > 0:
            msg = f"✅ Đã quét thủ công: {total_found} video mới từ {num_channels} kênh."
        else:
            default_min = get_default_min_views(db)
            msg = f"Đã quét {num_channels} kênh. 0 video đạt ngưỡng {default_min:,} views."
    except Exception as e:
        msg = f"❌ Lỗi quét: {str(e)[:120]}"
    return HTMLResponse(content=_render_viral_tbody(request, db, scan_message=msg))


def _render_viral_settings(
    viral_min_views: int,
    viral_max_videos: int,
    saved: bool = False,
) -> str:
    """Fragment HTML cho block cài đặt Viral (sau khi Lưu)."""
    vmin = max(500, min(10_000_000, int(viral_min_views)))
    vmax = max(0, min(500, int(viral_max_videos))) if viral_max_videos is not None else 50
    # 0 = "lấy hết" (backend dùng 500), hiển thị 0 cho user
    msg = ' <span class="text-green-600 text-xs">Đã lưu.</span>' if saved else ''
    return (
        f'<div id="viral-settings" class="flex items-center gap-3 flex-wrap">'
        f'<label class="text-sm text-gray-600 flex items-center gap-2">'
        f'Ngưỡng view tối thiểu: '
        f'<input type="number" name="viral_min_views" value="{vmin}" min="500" max="10000000" step="500" '
        f'class="w-24 border border-gray-300 rounded px-2 py-1 text-sm"> '
        f'<span class="text-gray-400 text-xs">views</span></label>'
        f'<label class="text-sm text-gray-600 flex items-center gap-2">'
        f'Số video tối đa mỗi kênh: '
        f'<input type="number" name="viral_max_videos_per_channel" value="{vmax}" min="0" max="500" '
        f'class="w-20 border border-gray-300 rounded px-2 py-1 text-sm" title="0 = lấy tối đa (cap 500)">'
        f'</label>'
        f'<button type="button" hx-post="/viral/settings" hx-include="[name=\'viral_min_views\'], [name=\'viral_max_videos_per_channel\']" '
        f'hx-target="#viral-settings" hx-swap="outerHTML" '
        f'class="text-sm bg-gray-600 hover:bg-gray-700 text-white px-3 py-1 rounded">Lưu</button>'
        f'{msg}</div>'
    )


@router.post("/settings", response_class=HTMLResponse)
def save_viral_settings(
    viral_min_views: int = Form(10000),
    viral_max_videos_per_channel: int = Form(50),
    db: Session = Depends(get_db),
):
    """Lưu cài đặt quét Viral (ngưỡng view + số video tối đa mỗi kênh)."""
    vmin = max(500, min(10_000_000, int(viral_min_views)))
    vmax_raw = int(viral_max_videos_per_channel) if viral_max_videos_per_channel is not None else 50
    vmax = max(0, min(500, vmax_raw))  # 0 = "lấy hết" (backend sẽ dùng 500)
    state = WorkerService.get_or_create_state(db)
    state.viral_min_views = vmin
    state.viral_max_videos_per_channel = vmax  # 0 = lấy hết (backend cap 500)
    db.commit()
    return HTMLResponse(content=_render_viral_settings(vmin, vmax, saved=True))


@router.post("/{material_id}/delete", response_class=HTMLResponse)
def delete_material(material_id: int, db: Session = Depends(get_db)):
    material = db.query(ViralMaterial).filter(ViralMaterial.id == material_id).first()
    if material:
        db.delete(material)
        db.commit()
    return HTMLResponse(content="")
