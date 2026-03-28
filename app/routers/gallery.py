from fastapi import APIRouter, Depends, Request, File, UploadFile, Form
from fastapi.responses import HTMLResponse, JSONResponse
import os
import time
import shutil
import uuid
import logging
from sqlalchemy.orm import Session
from app.database.core import get_db, SessionLocal
from app.database.models import Account, Job
from app.main_templates import templates

router = APIRouter(prefix="/gallery", tags=["gallery"])
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONTENT_DIR = os.path.join(BASE_DIR, "content")


def _scan_dir(folder: str, max_items: int = 200) -> list[dict]:
    """Scan a directory and return file metadata."""
    result = []
    sub = os.path.join(CONTENT_DIR, folder)
    if not os.path.isdir(sub):
        return result
    
    try:
        entries = sorted(os.scandir(sub), key=lambda e: e.stat().st_mtime, reverse=True)
    except Exception:
        return result
        
    for entry in entries[:max_items]:
        if not entry.is_file():
            continue
        ext = entry.name.lower().rsplit(".", 1)[-1] if "." in entry.name else ""
        kind = "video" if ext in ("mp4", "webm", "mov", "avi", "mkv") else ("image" if ext in ("jpg", "jpeg", "png", "gif", "webp") else "other")
        if kind == "other":
            continue
        stat = entry.stat()
        result.append({
            "name": entry.name,
            "path": entry.path,
            "folder": folder,
            "url": f"/gallery/media/{folder}/{entry.name}",
            "kind": kind,
            "size_kb": round(stat.st_size / 1024, 1),
            "mtime": int(stat.st_mtime),
            "mtime_str": time.strftime("%H:%M %d/%m", time.localtime(stat.st_mtime)),
        })
    return result


@router.get("/", response_class=HTMLResponse)
def gallery_page(request: Request, folder: str = "raw"):
    """Main gallery page."""
    allowed = {"raw", "processed", "done", "manual", "reup"}
    if folder not in allowed:
        folder = "raw"
    items = _scan_dir(folder)
    return templates.TemplateResponse("pages/app_gallery.html", {
        "request": request,
        "items": items,
        "active_folder": folder,
        "folders": ["raw", "processed", "done", "manual", "reup"],
    })


@router.get("/fragment", response_class=HTMLResponse)
def gallery_fragment(request: Request, folder: str = "raw"):
    """HTMX fragment: just the grid of media items."""
    allowed = {"raw", "processed", "done", "manual", "reup"}
    if folder not in allowed:
        folder = "raw"
    items = _scan_dir(folder)
    return templates.TemplateResponse("fragments/gallery_grid.html", {
        "request": request,
        "items": items,
        "active_folder": folder,
    })


@router.delete("/delete", response_class=JSONResponse)
def gallery_delete(folder: str, name: str):
    """Delete a specific media file."""
    allowed = {"raw", "processed", "done", "manual", "reup"}
    if folder not in allowed:
        return JSONResponse({"error": "Invalid folder"}, status_code=400)
    path = os.path.join(CONTENT_DIR, folder, name)
    # Defensively ensure path doesn't escape the content directory
    if not os.path.realpath(path).startswith(os.path.realpath(CONTENT_DIR)):
        return JSONResponse({"error": "Forbidden path"}, status_code=403)
    try:
        os.remove(path)
        return JSONResponse({"ok": True, "deleted": name})
    except FileNotFoundError:
        return JSONResponse({"error": "File not found"}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
