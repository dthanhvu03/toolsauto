from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, FileResponse
import subprocess
import os
import json
import glob
import time
import shutil
import psutil
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from app.core.pm2_apps import PM2_SAFE_NAMES
from app.main_templates import templates
from app.core.database.core import SessionLocal, engine
from app.core.database.models import Job, Account
from app.constants import JobStatus
from app.config import (
    TIMEZONE,
    DATABASE_URL,
    BASE_DIR,
    DATA_DIR,
    REUP_DIR,
    THUMB_DIR,
    THREADS_MEDIA_DIR,
    LOGS_DIR,
    DEBUG_STEPS_DIR,
    VNC_PORT,
    CONTENT_MEDIA_DIR,
    CONTENT_PROCESSED_DIR,
    SYSPANEL_DESTRUCTIVE_ENABLED,
    iter_pm2_log_directories,
)
from pathlib import Path
import app.config as config

router = APIRouter(prefix="/syspanel", tags=["syspanel"])
logger = logging.getLogger(__name__)

APP_DIR = str(BASE_DIR)


def _get_pm2_log_path(worker: str, log_type: str) -> str:
    """Scan các thư mục PM2 log phổ biến — không dùng pm2 jlist (lỗi socket permission)."""
    # PM2 log filename: dùng trực tiếp tên process nếu có dấu "-" (vd: ai-worker)
    # Nếu không có "-", PM2 thay "_" bằng "-" (vd: FB_Publisher → FB-Publisher)
    if "-" in worker:
        log_name = worker  # giữ nguyên: ai-worker → ai-worker-out.log
    else:
        log_name = worker.replace("_", "-")  # FB_Publisher → FB-Publisher
    suffix = f"{log_name}-{log_type}.log"

    for d in iter_pm2_log_directories():
        path = os.path.join(str(d), suffix)
        if os.path.exists(path):
            return path

    first = next(iter(iter_pm2_log_directories()), None)
    base = str(first) if first else os.path.expanduser("~/.pm2/logs")
    return os.path.join(base, suffix)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def run_cmd(cmd: str, cwd: str = None, timeout: int = 120) -> str:
    try:
        result = subprocess.run(
            cmd, shell=True, cwd=cwd or APP_DIR,
            capture_output=True, text=True, timeout=timeout
        )
        out = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
        return out.strip() or "✅ Done (no output)."
    except subprocess.TimeoutExpired:
        return "❌ Timeout: command took too long."
    except Exception as e:
        return f"❌ Error: {e}"


def _html_output(text: str) -> HTMLResponse:
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return HTMLResponse(f"<pre class='text-sm text-green-400 font-mono whitespace-pre-wrap leading-relaxed'>{escaped}</pre>")


def _colorize_log_lines(escaped: str) -> str:
    lines = escaped.split("\n")
    result = []
    for line in lines:
        if "[ERROR]" in line or "[EXCEPTION]" in line:
            result.append(f"<span class='text-red-400 font-semibold'>{line}</span>")
        elif "[WARNING]" in line or "[WARN]" in line:
            result.append(f"<span class='text-yellow-400'>{line}</span>")
        elif "[DEBUG]" in line:
            result.append(f"<span class='text-gray-500'>{line}</span>")
        else:
            result.append(line)
    return "\n".join(result)


# Whitelist PM2 process names — single source: app.core.pm2_apps
# (PM2_SAFE_NAMES imported above)


def _parse_pm2_proc(p: dict) -> dict:
    """Parse a single PM2 jlist entry into a clean dict."""
    mem = p.get("monit", {}).get("memory", 0)
    cpu = p.get("monit", {}).get("cpu", 0)
    status = p.get("pm2_env", {}).get("status", "unknown")
    restarts = p.get("pm2_env", {}).get("restart_time", 0)
    uptime_ms = p.get("pm2_env", {}).get("pm_uptime", None)
    pid = p.get("pid", "-")
    if uptime_ms:
        secs = int((time.time() * 1000 - uptime_ms) / 1000)
    else:
        secs = 0
    if secs < 60:
        uptime_str = f"{secs}s"
    elif secs < 3600:
        uptime_str = f"{secs // 60}m {secs % 60}s"
    else:
        uptime_str = f"{secs // 3600}h {(secs % 3600) // 60}m"
    return {
        "id": p.get("pm_id"),
        "name": p.get("name"),
        "status": status,
        "cpu": cpu,
        "mem_mb": round(mem / (1024 * 1024), 1),
        "restarts": restarts,
        "uptime": uptime_str,
        "pid": pid,
    }


def _get_pm2_processes():
    """
    Returns (procs, meta).
    meta.mode: ok | empty | missing | error
    """
    meta = {"mode": "empty", "detail": ""}
    try:
        which = shutil.which("pm2")
        if not which:
            # Windows local thường chạy start.ps1/uvicorn — không cài PM2
            meta = {
                "mode": "missing",
                "detail": "Không tìm thấy lệnh `pm2` trên PATH. Máy local thường chạy Web qua start.ps1 — không phải hệ thống down.",
            }
            return [], meta
        result = subprocess.run(
            "pm2 jlist",
            shell=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        raw = (result.stdout or "").strip()
        if not raw:
            err = (result.stderr or "").strip()
            meta = {
                "mode": "empty" if result.returncode == 0 else "error",
                "detail": err or "pm2 jlist không trả về process nào.",
            }
            return [], meta
        data = json.loads(raw)
        procs = [_parse_pm2_proc(p) for p in data]
        meta = {"mode": "ok" if procs else "empty", "detail": ""}
        return procs, meta
    except Exception as e:
        return [], {"mode": "error", "detail": str(e)}


def _get_pm2_process_by_name(name: str) -> dict | None:
    """Fetch a single PM2 process by name, for HTMX partial row swap."""
    procs, _meta = _get_pm2_processes()
    for p in procs:
        if p.get("name") == name:
            return p
    return None


def _dir_file_stats(path: Path) -> dict:
    """Đếm file đệ quy + size (MB chính xác hơn round GB sớm)."""
    count = 0
    total_bytes = 0
    if not path.is_dir():
        return {"count": 0, "size_gb": 0.0, "size_mb": 0.0, "exists": False}
    try:
        for f in path.rglob("*"):
            try:
                if f.is_file():
                    count += 1
                    total_bytes += f.stat().st_size
            except OSError:
                continue
    except OSError:
        pass
    return {
        "count": count,
        "size_gb": round(total_bytes / (1024**3), 3),
        "size_mb": round(total_bytes / (1024**2), 1),
        "exists": True,
    }


def _get_content_stats():
    # No video/done/failed dirs: legacy empty folders — cleanup deletes media in place.
    # Upload via UI → media/; viral → REUP_DIR; ffmpeg → processed. See docs/CONFIG.md.
    mapping = {
        "media": CONTENT_MEDIA_DIR,
        "processed": CONTENT_PROCESSED_DIR,
        "reup": REUP_DIR,
        "thumbnails": THUMB_DIR,
        "threads_media": THREADS_MEDIA_DIR,
    }
    return {folder: _dir_file_stats(Path(path)) for folder, path in mapping.items()}


def _safe_tz():
    """IANA zone nếu có; Windows thiếu tzdata → local timezone."""
    try:
        return ZoneInfo(TIMEZONE)
    except Exception:
        return datetime.now().astimezone().tzinfo


def _format_ts(ts: float, fmt: str = "%H:%M %d/%m") -> str:
    return datetime.fromtimestamp(ts, tz=_safe_tz()).strftime(fmt)


def _get_screenshots():
    """
    Thu thập screenshot debug/bot.
    Adapter ghi logs/<platform>/job_*.png và logs/debug_steps/ — cần scan đệ quy.
    Không quét CONTENT_DIR / APP_DIR (tránh ảnh content & file trong venv).
    """
    roots = [
        Path(LOGS_DIR),
        Path(DEBUG_STEPS_DIR),
        Path(DATA_DIR),  # debug_comment_*.png legacy
    ]
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    skip_dir_names = {
        "venv", ".venv", "node_modules", ".git", "profiles",
        "Cache", "Cache_Data", "__pycache__", "backups",
    }
    name_ok = (
        "job_", "debug_", "timeout_", "gemini_", "video_upload",
        "screenshot", "fail", "error", "proof",
    )

    shots: list[tuple[float, Path]] = []
    seen: set[str] = set()
    logs_root = Path(LOGS_DIR).resolve()

    for root in roots:
        root = Path(root)
        if not root.is_dir():
            continue
        for f in root.rglob("*"):
            try:
                if not f.is_file() or f.suffix.lower() not in exts:
                    continue
                if any(part in skip_dir_names for part in f.parts):
                    continue
                resolved = f.resolve()
                under_logs = logs_root == resolved.parent or logs_root in resolved.parents
                if not under_logs:
                    low = f.name.lower()
                    if not any(tok in low for tok in name_ok):
                        continue
                key = str(resolved)
                if key in seen:
                    continue
                seen.add(key)
                shots.append((f.stat().st_mtime, f))
            except OSError:
                continue

    shots.sort(key=lambda x: x[0], reverse=True)
    return [str(p) for _, p in shots[:24]]


# ─── Main Page ───────────────────────────────────────────────────────────────

def get_syspanel(request: Request):
    # One-shot: nếu VPS còn ai_persona.json lệch DB → đẩy vào AI Studio general.
    try:
        migrate_persona_file_to_studio_if_needed()
    except Exception as e:
        logger.warning("persona migrate skipped: %s", e)
    return templates.TemplateResponse("pages/syspanel.html", {"request": request})


# ─── Live Fragments ───────────────────────────────────────────────────────────

def frag_metrics(request: Request):
    cpu = psutil.cpu_percent(interval=0.2)
    mem = psutil.virtual_memory()
    # Disk của ổ chứa project (không dùng "/" — trên Windows dễ nhầm ổ khác)
    disk_path = str(BASE_DIR)
    try:
        disk = psutil.disk_usage(disk_path)
    except OSError:
        disk = psutil.disk_usage("/")
        disk_path = "/"
    disk_label = Path(disk_path).drive or disk_path
    net = psutil.net_io_counters()
    boot_ts = psutil.boot_time()
    uptime_secs = int(time.time() - boot_ts)
    h = uptime_secs // 3600
    m = (uptime_secs % 3600) // 60

    def color(pct):
        if pct < 60:
            return "bg-emerald-500"
        elif pct < 80:
            return "bg-amber-400"
        return "bg-red-500"

    ctx = {
        "request": request,
        "cpu": cpu, "cpu_color": color(cpu),
        "mem_pct": mem.percent, "mem_color": color(mem.percent),
        "mem_used": round(mem.used / 1024**3, 2), "mem_total": round(mem.total / 1024**3, 2),
        "disk_pct": disk.percent, "disk_color": color(disk.percent),
        "disk_used": round(disk.used / 1024**3, 2), "disk_total": round(disk.total / 1024**3, 2),
        "disk_label": disk_label,
        "net_sent_mb": round(net.bytes_sent / 1024**2, 1),
        "net_recv_mb": round(net.bytes_recv / 1024**2, 1),
        "uptime": f"{h}h {m}m",
    }
    return templates.TemplateResponse("fragments/syspanel/metrics.html", ctx)


def frag_pm2(request: Request):
    procs, meta = _get_pm2_processes()
    return templates.TemplateResponse("fragments/syspanel/pm2_table.html", {
        "request": request,
        "procs": procs,
        "pm2_mode": meta.get("mode", "empty"),
        "pm2_detail": meta.get("detail", ""),
    })


def frag_job_stats(request: Request):
    db = SessionLocal()
    try:
        rows = db.execute(
            __import__("sqlalchemy").text("SELECT status, COUNT(*) as cnt FROM jobs GROUP BY status")
        ).fetchall()
        stats = {r[0]: r[1] for r in rows}
        total = sum(stats.values())
        total_accounts = db.query(Account).count()
        total_materials = db.execute(
            __import__("sqlalchemy").text("SELECT COUNT(*) FROM viral_materials")
        ).scalar()
    finally:
        db.close()
    return templates.TemplateResponse("fragments/syspanel/job_stats.html", {
        "request": request,
        "stats": stats, "total": total,
        "total_accounts": total_accounts,
        "total_materials": total_materials,
    })


def frag_content_stats(request: Request):
    stats = _get_content_stats()
    return templates.TemplateResponse("fragments/syspanel/content_stats.html", {
        "request": request, "stats": stats
    })





def frag_gemini_cookies(request: Request):
    cookie_path = str(config.GEMINI_COOKIES_FILE)
    invalid_flag = str(config.GEMINI_COOKIES_INVALID_FLAG)

    has_invalid_flag = os.path.exists(invalid_flag)
    file_exists = os.path.exists(cookie_path)
    cookies = []
    file_size = 0
    file_mtime = None
    key_cookies = []
    error = None

    if file_exists:
        try:
            file_size = round(os.path.getsize(cookie_path) / 1024, 1)
            mtime = os.path.getmtime(cookie_path)
            file_mtime = _format_ts(mtime, "%H:%M:%S %d/%m/%Y")
            with open(cookie_path) as f:
                cookies = json.load(f)
            # Extract key cookies info
            KEY_NAMES = ["__Secure-1PSID", "__Secure-1PSIDTS", "__Secure-3PSID", "SID", "HSID", "SSID", "APISID", "SAPISID"]
            now_ts = time.time()
            for c in cookies:
                if c.get("name") in KEY_NAMES:
                    expiry = c.get("expiry", 0)
                    expired = expiry > 0 and expiry < now_ts
                    exp_str = _format_ts(expiry, "%d/%m/%Y") if expiry else "session"
                    key_cookies.append({
                        "name": c.get("name"),
                        "domain": c.get("domain", ""),
                        "expiry_str": exp_str,
                        "expired": expired,
                        "value_preview": (c.get("value") or "")[:20] + "…",
                    })
        except Exception as e:
            error = str(e)

    overall_ok = file_exists and not has_invalid_flag and len(cookies) > 0 and not error

    return templates.TemplateResponse("fragments/syspanel/gemini_cookies.html", {
        "request": request,
        "file_exists": file_exists,
        "has_invalid_flag": has_invalid_flag,
        "file_size_kb": file_size,
        "file_mtime": file_mtime,
        "total_cookies": len(cookies),
        "key_cookies": key_cookies,
        "overall_ok": overall_ok,
        "error": error,
        "cookie_path": cookie_path,
    })


def frag_screenshots(request: Request):
    shots = _get_screenshots()
    root = Path(APP_DIR).resolve()
    rel_shots = []
    for s in shots:
        abs_path = Path(s).resolve()
        try:
            rel = abs_path.relative_to(root).as_posix()
        except ValueError:
            # Ngoài APP_DIR — vẫn serve bằng abs (serve sẽ chặn nếu ngoài root)
            rel = str(abs_path)
        name = abs_path.name
        try:
            mtime = _format_ts(abs_path.stat().st_mtime)
        except OSError:
            mtime = "—"
        rel_shots.append({"path": rel, "name": name, "mtime": mtime})
    return templates.TemplateResponse("fragments/syspanel/screenshots.html", {
        "request": request, "shots": rel_shots
    })


# ─── Log Viewer ──────────────────────────────────────────────────────────────

def get_logs(request: Request, worker: str = "Web_Dashboard", log_type: str = "error", lines: int = 100):
    # Bao gồm cả process names của root PM2 (production) và vu PM2 (dev)
    safe_workers = [
        "FB_Publisher_1", "FB_Publisher_2", "AI_Generator_1", "AI_Generator_2",  # scaled
        "FB_Publisher", "AI_Generator", "Maintenance", "Web_Dashboard",          # legacy
        "9Router_Gateway",
        "ai-worker", "publisher", "maintenance", "web", "ai", "worker",           # root PM2
    ]
    if worker not in safe_workers:
        worker = "Web_Dashboard"
    log_type = "error" if log_type == "error" else "out"
    log_file = _get_pm2_log_path(worker, log_type)

    content = None
    if os.path.exists(log_file):
        # File readable bình thường
        result = subprocess.run(f"tail -n {lines} '{log_file}'", shell=True, capture_output=True, text=True)
        content = result.stdout or "(empty)"
    else:
        # Thử đọc bằng sudo (cho /root/.pm2/logs/ không accessible từ user vu)
        result = subprocess.run(
            f"sudo tail -n {lines} '{log_file}' 2>/dev/null",
            shell=True, capture_output=True, text=True, timeout=5
        )
        if result.stdout.strip():
            content = result.stdout

    if content is None:
        # Liệt kê tất cả file log tìm được để debug
        all_logs = []
        for d in iter_pm2_log_directories():
            d = str(d)
            try:
                all_logs += [f"{d}/{f}" for f in os.listdir(d) if f.endswith(".log")]
            except Exception:
                all_logs.append(f"{d}: permission denied")
        content = (
            f"Log file not found or not readable: {log_file}\n\n"
            f"Available log files:\n" + "\n".join(f"  {x}" for x in all_logs)
        )
    escaped = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    colorized = _colorize_log_lines(escaped)
    return HTMLResponse(f"<pre class='text-xs text-green-400 font-mono whitespace-pre-wrap leading-relaxed'>{colorized}</pre>")


# ─── Screenshot Serve ─────────────────────────────────────────────────────────

def serve_screenshot(path: str):
    """Serve screenshot by relative path under APP_DIR (hoặc abs trong APP_DIR)."""
    try:
        raw = (path or "").strip()
        candidate = Path(raw)
        root = Path(APP_DIR).resolve()
        if candidate.is_absolute():
            abs_path = candidate.resolve()
        else:
            abs_path = (root / candidate).resolve()
        abs_path.relative_to(root)
    except (OSError, ValueError):
        return HTMLResponse("Forbidden", status_code=403)
    if not abs_path.exists() or not abs_path.is_file():
        return HTMLResponse("Not found", status_code=404)
    return FileResponse(str(abs_path))


# ─── Action Commands ──────────────────────────────────────────────────────────

def _destructive_blocked(action: str) -> HTMLResponse | None:
    if SYSPANEL_DESTRUCTIVE_ENABLED:
        return None
    return _html_output(
        f"Blocked: '{action}' requires SYSPANEL_DESTRUCTIVE_ENABLED=true in .env"
    )


def cmd_git_pull():
    blocked = _destructive_blocked("git reset --hard")
    if blocked:
        return blocked
    # Prefer current upstream branch; fall back to develop for legacy VPS scripts.
    out = run_cmd(
        "git fetch origin && "
        "branch=$(git rev-parse --abbrev-ref HEAD) && "
        "git reset --hard \"origin/$branch\""
    )
    return _html_output(f"$ git fetch + reset --hard origin/<current-branch>\n\n{out}")


def cmd_pm2_restart():
    blocked = _destructive_blocked("pm2 restart all")
    if blocked:
        return blocked
    out = run_cmd("pm2 restart all")
    return _html_output(f"$ pm2 restart all\n\n{out}")


def cmd_pm2_restart_one(name: str = Form(...)):
    if name not in PM2_SAFE_NAMES:
        return _html_output(f"Unknown process: {name}")
    out = run_cmd(f"pm2 restart {name}")
    return _html_output(f"$ pm2 restart {name}\n\n{out}")


def cmd_pm2_action(request: Request, action: str = Form(...), name: str = Form(...)):
    """Unified PM2 action endpoint — returns HTMX row fragment for OOB swap."""
    if name not in PM2_SAFE_NAMES:
        return HTMLResponse(
            f"<tr><td colspan='7' class='py-2 text-red-500 text-sm'>Unknown process: {name}</td></tr>",
            status_code=400,
        )
    if action not in ("start", "stop", "restart"):
        return HTMLResponse(
            f"<tr><td colspan='7' class='py-2 text-red-500 text-sm'>Invalid action: {action}</td></tr>",
            status_code=400,
        )

    run_cmd(f"pm2 {action} {name}")
    # Brief pause for PM2 to update status
    time.sleep(0.5)

    proc = _get_pm2_process_by_name(name)
    if proc:
        return templates.TemplateResponse("fragments/syspanel/pm2_row.html", {
            "request": request, "p": proc,
        })
    # Fallback: process disappeared (deleted) — return empty row with message
    return HTMLResponse(
        f"<tr><td colspan='7' class='py-2 text-gray-400 text-sm italic'>{name} — removed</td></tr>"
    )


def cmd_pm2_start():
    out = run_cmd("bash start.sh")
    return _html_output(f"$ bash start.sh\n\n{out}")


def cmd_pm2_stop():
    blocked = _destructive_blocked("pm2 delete all")
    if blocked:
        return blocked
    out = run_cmd("pm2 delete all")
    return _html_output(f"$ pm2 delete all\n\n{out}")


def cmd_kill_chrome():
    chrome_out = run_cmd("pkill -f 'chrome' && echo 'Chrome killed' || echo 'No Chrome process found'")
    xvfb_out = run_cmd("pkill -f 'Xvfb' && echo 'Xvfb killed' || echo 'No Xvfb process found'")
    return _html_output(f"$ pkill chrome\n{chrome_out}\n\n$ pkill Xvfb\n{xvfb_out}")


def cmd_start_vnc(request: Request):
    """Delegate VNC startup to the specialized script for better stability."""
    # Correct paths: script and venv are inside BASE_DIR (which APP_DIR points to)
    script_path = os.path.join(APP_DIR, "scripts", "start_vps_vnc.py")
    python_path = os.path.join(APP_DIR, "venv", "bin", "python")
    
    cmd = f"{python_path} {script_path}"
    out = run_cmd(cmd)
    
    # Get dynamic host for the link
    host = request.client.host
    if request.headers.get("host"):
        host = request.headers["host"].split(":")[0]
    
    # Check if failed or success based on output
    status_icon = "✅" if "[OK]" in out else "⚠️"
    msg = f"{status_icon} VNC Startup Result:\n\n{out}\n\nLink: http://{host}:{VNC_PORT}/vnc.html"
    return _html_output(msg)


def cmd_stop_vnc():
    out_vnc = run_cmd("pkill -f x11vnc && echo 'x11vnc killed' || echo 'No x11vnc process found'")
    out_web = run_cmd("pkill -f websockify && echo 'websockify killed' || echo 'No websockify process found'")
    return _html_output(f"🛑 VNC Stream Stopped\n\n$ pkill x11vnc\n{out_vnc}\n\n$ pkill websockify\n{out_web}")


def cmd_cleanup_db():
    """Chạy script dọn page rác — path archive; dùng interpreter hiện tại (Windows/Linux)."""
    import sys
    script = os.path.join(APP_DIR, "scripts", "archive", "fix_garbage_pages.py")
    if not os.path.isfile(script):
        return _html_output(
            "Cleanup script không còn ở scripts/fix_garbage_pages.py "
            "(đã chuyển sang scripts/archive/). Không chạy được."
        )
    out = run_cmd(f'"{sys.executable}" "{script}"')
    return _html_output(f"$ python scripts/archive/fix_garbage_pages.py\n\n{out}")


def cmd_db_vacuum():
    """Run PostgreSQL VACUUM ANALYZE on all tables."""
    try:
        from sqlalchemy import text as sa_text
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(sa_text("VACUUM ANALYZE"))
        return _html_output("VACUUM ANALYZE completed successfully.")
    except Exception as e:
        return _html_output(f"VACUUM error: {e}")


def cmd_db_backup():
    """Backup PostgreSQL database using pg_dump (local PATH hoặc docker exec)."""
    try:
        import gzip
        import shutil
        from urllib.parse import urlparse

        parsed = urlparse(DATABASE_URL.replace("postgresql+psycopg2://", "postgresql://"))
        db_host = parsed.hostname or "localhost"
        db_port = str(parsed.port or 5432)
        db_name = (parsed.path or "/toolsauto_db").lstrip("/")
        db_user = parsed.username or "admin"
        db_pass = parsed.password or ""

        backup_dir = DATA_DIR / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        try:
            ts = datetime.now(tz=ZoneInfo(TIMEZONE)).strftime("%Y%m%d_%H%M%S")
        except Exception:
            # Windows thiếu tzdata / IANA zone → fallback local time
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"{db_name}_{ts}.sql.gz"
        backup_path_str = str(backup_path)

        env = os.environ.copy()
        if db_pass:
            env["PGPASSWORD"] = db_pass

        dump_bytes = None
        method = ""

        if shutil.which("pg_dump"):
            method = "pg_dump"
            result = subprocess.run(
                [
                    "pg_dump",
                    "-h", db_host,
                    "-p", db_port,
                    "-U", db_user,
                    "-d", db_name,
                    "--no-owner",
                    "--no-acl",
                ],
                capture_output=True,
                timeout=300,
                env=env,
            )
            if result.returncode != 0:
                err = (result.stderr or b"").decode("utf-8", errors="replace").strip()
                return _html_output(f"Backup failed (exit {result.returncode}):\n{err}")
            dump_bytes = result.stdout
        elif shutil.which("docker"):
            container = (os.getenv("POSTGRES_DOCKER_CONTAINER") or "toolsauto_postgres").strip()
            method = f"docker exec {container}"
            cmd = [
                "docker", "exec",
                "-e", f"PGPASSWORD={db_pass}",
                container,
                "pg_dump", "-U", db_user, "-d", db_name, "--no-owner", "--no-acl",
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=300)
            if result.returncode != 0:
                err = (result.stderr or b"").decode("utf-8", errors="replace").strip()
                return _html_output(
                    f"Backup failed via docker (exit {result.returncode}):\n{err}\n"
                    f"Hint: set POSTGRES_DOCKER_CONTAINER=... or install pg_dump in PATH."
                )
            dump_bytes = result.stdout
        else:
            return _html_output(
                "Backup failed: không tìm thấy `pg_dump` trong PATH và không có `docker`.\n"
                "Cài PostgreSQL client tools hoặc chạy Postgres trong Docker (toolsauto_postgres)."
            )

        with gzip.open(backup_path_str, "wb") as fh:
            fh.write(dump_bytes or b"")

        size_mb = os.path.getsize(backup_path_str) / 1024**2
        return _html_output(
            f"Backup created successfully ({method}):\n"
            f"File: {backup_path_str}\n"
            f"Size: {size_mb:.2f} MB"
        )
    except subprocess.TimeoutExpired:
        return _html_output("Backup failed: pg_dump timed out (>5 min).")
    except Exception as e:
        return _html_output(f"Backup failed: {e}")


def cmd_db_info():
    """Show PostgreSQL database info: version, size, connections, top tables."""
    try:
        from sqlalchemy import text as sa_text
        lines = []
        with engine.connect() as conn:
            # PG version
            ver = conn.execute(sa_text("SELECT version()")).scalar()
            lines.append(f"PostgreSQL Version:\n  {ver}")

            # DB size
            db_size = conn.execute(sa_text(
                "SELECT pg_size_pretty(pg_database_size(current_database()))"
            )).scalar()
            lines.append(f"\nDatabase Size: {db_size}")

            # Active connections
            conns = conn.execute(sa_text(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
            )).scalar()
            lines.append(f"Active Connections: {conns}")

            # Top 10 tables by size (join on relid — tránh AmbiguousColumn relname)
            rows = conn.execute(sa_text(
                "SELECT c.relname AS table_name, "
                "pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size, "
                "s.n_live_tup AS row_count "
                "FROM pg_class c "
                "JOIN pg_stat_user_tables s ON s.relid = c.oid "
                "WHERE c.relkind = 'r' "
                "ORDER BY pg_total_relation_size(c.oid) DESC "
                "LIMIT 10"
            )).fetchall()
            lines.append("\nTop 10 Tables (by size):")
            lines.append(f"  {'Table':<30} {'Size':<12} {'Rows':>10}")
            lines.append(f"  {'-'*30} {'-'*12} {'-'*10}")
            for r in rows:
                lines.append(f"  {r[0]:<30} {r[1]:<12} {r[2]:>10}")

        return _html_output("\n".join(lines))
    except Exception as e:
        return _html_output(f"DB Info error: {e}")


def cmd_cleanup_videos():
    """Delete media files for DONE jobs older than 7 days."""
    db = SessionLocal()
    cutoff = int(time.time()) - 7 * 86400
    try:
        done_jobs = db.query(Job).filter(
            Job.status == JobStatus.DONE,
            Job.finished_at != None,
            Job.finished_at < cutoff
        ).all()
        deleted = 0
        freed_bytes = 0
        errors = []
        for job in done_jobs:
            for path_attr in ["media_path", "processed_media_path"]:
                p = getattr(job, path_attr, None)
                if p and os.path.exists(p):
                    try:
                        freed_bytes += os.path.getsize(p)
                        os.unlink(p)
                        deleted += 1
                    except Exception as e:
                        errors.append(str(e))
        freed_mb = freed_bytes / 1024**2
        err_str = f"\n⚠️ Errors:\n" + "\n".join(errors[:5]) if errors else ""
        return _html_output(
            f"✅ Cleaned {deleted} video files from DONE jobs older than 7 days\n"
            f"💾 Freed: {freed_mb:.1f} MB{err_str}"
        )
    finally:
        db.close()


def cmd_retry_failed():
    """Bulk retry all FAILED jobs."""
    db = SessionLocal()
    try:
        failed = db.query(Job).filter(Job.status == JobStatus.FAILED).all()
        count = len(failed)
        for job in failed:
            job.status = JobStatus.PENDING
            job.tries = 0
            job.locked_at = None
        db.commit()
        return _html_output(f"✅ Retried {count} FAILED jobs → PENDING")
    except Exception as e:
        db.rollback()
        return _html_output(f"❌ Error: {e}")
    finally:
        db.close()


def cmd_cancel_stuck():
    """Cancel RUNNING jobs that haven't had a heartbeat in 10 min."""
    db = SessionLocal()
    cutoff = int(time.time()) - 600
    try:
        stuck = db.query(Job).filter(
            Job.status == JobStatus.RUNNING,
            Job.last_heartbeat_at < cutoff
        ).all()
        count = len(stuck)
        for job in stuck:
            job.status = JobStatus.FAILED
            job.last_error = "Cancelled: no heartbeat for 10+ min (manual syspanel)"
        db.commit()
        return _html_output(f"✅ Cancelled {count} stuck RUNNING jobs → FAILED")
    except Exception as e:
        db.rollback()
        return _html_output(f"❌ Error: {e}")
    finally:
        db.close()


def cmd_clear_gemini_cookies():
    """Delete Gemini cookie file and invalid flag."""
    cookie_path = str(config.GEMINI_COOKIES_FILE)
    invalid_flag = str(config.GEMINI_COOKIES_INVALID_FLAG)
    msgs = []
    if os.path.exists(cookie_path):
        os.unlink(cookie_path)
        msgs.append("✅ Đã xóa gemini_cookies.json")
    else:
        msgs.append("ℹ️ gemini_cookies.json không tồn tại")
    if os.path.exists(invalid_flag):
        os.unlink(invalid_flag)
        msgs.append("✅ Đã xóa gemini_cookies_invalid flag")
    return _html_output("\n".join(msgs))


# ─── Persona Tuner (retired → AI Studio) ──────────────────────────────────────

PERSONA_FILE = str(config.AI_PERSONA_FILE)  # giữ path; không xóa file nếu còn trên disk
_PERSONA_MIGRATED_FLAG = PERSONA_FILE + ".migrated_to_studio"


def migrate_persona_file_to_studio_if_needed() -> None:
    """Nếu còn ai_persona.json và khác ai.prompt.general → upsert một lần rồi đánh dấu."""
    if os.path.exists(_PERSONA_MIGRATED_FLAG):
        return
    if not os.path.isfile(PERSONA_FILE):
        # Không có file → đánh dấu luôn để khỏi check mỗi request
        try:
            open(_PERSONA_MIGRATED_FLAG, "a", encoding="utf-8").close()
        except Exception:
            pass
        return

    try:
        with open(PERSONA_FILE, "r", encoding="utf-8") as f:
            file_prompt = (json.load(f).get("system_prompt") or "").strip()
    except Exception:
        return
    if not file_prompt:
        open(_PERSONA_MIGRATED_FLAG, "a", encoding="utf-8").close()
        return

    from app.core import settings as runtime_settings
    db = SessionLocal()
    try:
        db_prompt = (runtime_settings.get_str("ai.prompt.general", db=db) or "").strip()
        if file_prompt != db_prompt:
            runtime_settings.upsert_setting(
                db,
                "ai.prompt.general",
                file_prompt,
                updated_by="syspanel_persona_retire",
            )
            logger.info("Migrated ai_persona.json → ai.prompt.general (%d chars)", len(file_prompt))
        open(_PERSONA_MIGRATED_FLAG, "w", encoding="utf-8").write(
            "migrated_or_skipped\n"
        )
    finally:
        db.close()


def _persona_retired_html() -> str:
    return (
        '<div class="text-sm text-[var(--color-mist)] leading-relaxed space-y-2">'
        '<p>AI Persona Tuner trên Panel hệ thống đã <strong class="text-[var(--color-ink-soft)]">ngừng dùng</strong>.</p>'
        '<p>Sửa giọng văn / prompt tại '
        '<a class="text-[var(--color-torch)] font-semibold underline" href="/app/ai-studio">AI Studio</a> '
        '(key <code>ai.prompt.*</code> — nguồn pipeline).</p>'
        '</div>'
    )


def get_persona_retired(request: Request):
    return HTMLResponse(_persona_retired_html(), status_code=410)


def save_persona_retired(system_prompt: str = Form("")):
    # Không ghi ai_persona.json — tránh UI giả hiệu lực.
    _ = system_prompt
    msg = (
        "Persona tuner đã retired. Không lưu file.\n"
        "Hãy sửa trên AI Studio: /app/ai-studio (ai.prompt.general / niche)."
    )
    escaped = msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return HTMLResponse(
        f"<pre class='text-sm text-green-400 font-mono whitespace-pre-wrap leading-relaxed'>{escaped}</pre>",
        status_code=410,
    )


# ─── 9Router UI ───────────────────────────────────────────────────────────────

def frag_9router_tuner(request: Request):
    from app.core.ai.runtime import pipeline
    from app.core.ai.pipeline import AICaptionPipeline

    # Config fields: read from this process's pipeline singleton (always up-to-date via reload_config)
    with pipeline._config_lock:
        is_enabled = pipeline.enabled
        base_url = pipeline.base_url
        default_model = pipeline.default_model

    api_key_masked = pipeline._get_masked_key()

    # Runtime stats: read from shared file written by AI_Generator process (cross-PM2 IPC)
    shared = AICaptionPipeline.load_shared_runtime_state()
    provider = shared.get("provider", "N/A")
    model = shared.get("model", "N/A")
    latency = shared.get("latency_ms", 0)
    msg = shared.get("fail_reason", "none")
    circuit_state = shared.get("circuit_state", pipeline.circuit_breaker.state.name)

    ctx = {
        "request": request,
        "is_enabled": is_enabled,
        "base_url": base_url,
        "api_key_masked": api_key_masked,
        "default_model": default_model,
        "circuit_state": circuit_state,
        "last_latency_ms": latency,
        "last_provider": provider,
        "last_model": model,
        "last_fail_reason": msg,
    }
    return templates.TemplateResponse("fragments/syspanel/9router_tuner.html", ctx)


def cmd_save_9router_config(
    enabled: str = Form("false"),
    base_url: str = Form(""),
    api_key: str = Form(""),
    default_model: str = Form("")
):
    from app.core.ai.runtime import pipeline
    
    config_path = pipeline.CONFIG_PATH
    is_enabled = enabled.lower() == "true"
    
    data = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except: pass
        
    data["enabled"] = is_enabled
    if base_url.strip():
        data["base_url"] = base_url.strip()
    elif "base_url" in data:
        del data["base_url"]
        
    if api_key and "••••••" not in api_key:
        data["api_key"] = api_key.strip()
    data["default_model"] = default_model.strip()
    
    try:
        # Đảm bảo thư mục runtime config tồn tại trước khi ghi file
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        success = pipeline.reload_config()
        if not success:
            return _html_output("❌ Lỗi: reload_config thất bại. Giữ nguyên cấu hình cũ.")
            
        return _html_output("✅ Cập nhật Config thành công & Đã reload nóng AI Pipeline!")
    except Exception as e:
        return _html_output(f"❌ Lỗi ghi file config: {e}")


def cmd_test_9router_connection(
    base_url: str = Form(""),
    api_key: str = Form(""),
    default_model: str = Form("")
):
    from app.core.ai.runtime import pipeline
    
    temp_key = api_key.strip()
    if temp_key and "••••••" in temp_key:
        with pipeline._config_lock:
            temp_key = pipeline.api_key
            
    res = pipeline.test_connection(base_url.strip(), temp_key, default_model.strip())
    
    if res["ok"]:
        html = f"✅ Kết nối thành công! ({res['latency_ms']}ms)\nModel: {res['model']}"
    else:
        html = f"❌ Kết nối thất bại: {res.get('message')}\nLý do: {res.get('fail_reason')}"
        
    return _html_output(html)
