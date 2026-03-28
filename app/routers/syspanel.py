from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, FileResponse
import subprocess
import os
import json
import glob
import time
import psutil
import shutil
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from app.main_templates import templates
from app.database.core import SessionLocal
from app.database.models import Job, Account
from app.config import TIMEZONE

router = APIRouter(prefix="/syspanel", tags=["syspanel"])
logger = logging.getLogger(__name__)

APP_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _get_pm2_log_path(worker: str, log_type: str) -> str:
    """Scan các thư mục PM2 log phổ biến — không dùng pm2 jlist (lỗi socket permission)."""
    # PM2 log filename: dùng trực tiếp tên process nếu có dấu "-" (vd: ai-worker)
    # Nếu không có "-", PM2 thay "_" bằng "-" (vd: FB_Publisher → FB-Publisher)
    if "-" in worker:
        log_name = worker  # giữ nguyên: ai-worker → ai-worker-out.log
    else:
        log_name = worker.replace("_", "-")  # FB_Publisher → FB-Publisher
    suffix = f"{log_name}-{log_type}.log"

    candidate_dirs = [
        "/home/vu/.pm2/logs",
        os.path.expanduser("~/.pm2/logs"),
        "/root/.pm2/logs",
    ]
    try:
        for entry in os.scandir("/home"):
            if entry.is_dir():
                candidate_dirs.append(f"/home/{entry.name}/.pm2/logs")
    except Exception:
        pass

    for d in candidate_dirs:
        path = os.path.join(d, suffix)
        if os.path.exists(path):
            return path

    return os.path.join(candidate_dirs[0], suffix)  # fallback — sẽ hiển thị error rõ ràng


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


def _get_pm2_processes():
    try:
        result = subprocess.run("pm2 jlist", shell=True, capture_output=True, text=True, timeout=10)
        data = json.loads(result.stdout)
        procs = []
        for p in data:
            mem = p.get("monit", {}).get("memory", 0)
            cpu = p.get("monit", {}).get("cpu", 0)
            status = p.get("pm2_env", {}).get("status", "unknown")
            restarts = p.get("pm2_env", {}).get("restart_time", 0)
            uptime_ms = p.get("pm2_env", {}).get("pm_uptime", None)
            created_at = p.get("pm2_env", {}).get("created_at", None)
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
            procs.append({
                "id": p.get("pm_id"),
                "name": p.get("name"),
                "status": status,
                "cpu": cpu,
                "mem_mb": round(mem / (1024 * 1024), 1),
                "restarts": restarts,
                "uptime": uptime_str,
                "pid": pid,
            })
        return procs
    except Exception:
        return []


def _get_content_stats():
    base = os.path.join(APP_DIR, "content")
    stats = {}
    for folder in ["media", "video", "done", "failed", "processed", "reup", "thumbnails"]:
        path = os.path.join(base, folder)
        if os.path.isdir(path):
            files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
            total_bytes = sum(os.path.getsize(os.path.join(path, f)) for f in files)
            stats[folder] = {"count": len(files), "size_gb": round(total_bytes / (1024**3), 2)}
        else:
            stats[folder] = {"count": 0, "size_gb": 0}
    return stats


def _get_screenshots():
    dirs = [
        os.path.join(APP_DIR, "logs"),
        os.path.join(APP_DIR, "content"),
        APP_DIR,
    ]
    shots = []
    for d in dirs:
        if os.path.isdir(d):
            for f in glob.glob(os.path.join(d, "*.png")) + glob.glob(os.path.join(d, "*.jpg")):
                shots.append((os.path.getmtime(f), f))
    shots.sort(reverse=True)
    return [f for _, f in shots[:12]]


# ─── Main Page ───────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def get_syspanel(request: Request):
    return templates.TemplateResponse("pages/syspanel.html", {"request": request})


# ─── Live Fragments ───────────────────────────────────────────────────────────

@router.get("/fragments/metrics", response_class=HTMLResponse)
def frag_metrics(request: Request):
    cpu = psutil.cpu_percent(interval=0.2)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
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
        "net_sent_mb": round(net.bytes_sent / 1024**2, 1),
        "net_recv_mb": round(net.bytes_recv / 1024**2, 1),
        "uptime": f"{h}h {m}m",
    }
    return templates.TemplateResponse("fragments/syspanel/metrics.html", ctx)


@router.get("/fragments/pm2", response_class=HTMLResponse)
def frag_pm2(request: Request):
    procs = _get_pm2_processes()
    return templates.TemplateResponse("fragments/syspanel/pm2_table.html", {
        "request": request, "procs": procs
    })


@router.get("/fragments/job-stats", response_class=HTMLResponse)
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


@router.get("/fragments/content-stats", response_class=HTMLResponse)
def frag_content_stats(request: Request):
    stats = _get_content_stats()
    return templates.TemplateResponse("fragments/syspanel/content_stats.html", {
        "request": request, "stats": stats
    })


@router.get("/fragments/db-explorer", response_class=HTMLResponse)
def frag_db_explorer(request: Request, table_name: str = None):
    if not table_name:
        return _html_output('<div class="text-sm text-gray-400">Please select a table to view data</div>')

    allowed_tables = {'accounts', 'jobs', 'pages', 'viral_materials', 'system_state'}
    if table_name not in allowed_tables:
        return _html_output('<div class="text-m text-red-500">Invalid table selected!</div>')

    try:
        import sqlite3
        db_path = os.path.join(APP_DIR, "data/auto_publisher.db")
        if not os.path.exists(db_path):
            return _html_output('<div class="text-sm text-red-500">Database file not found</div>')

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute(f"PRAGMA table_info({table_name})")
        columns_info = cur.fetchall()
        has_id = any(c['name'] == 'id' for c in columns_info)

        order_clause = "ORDER BY id DESC" if has_id else ""
        cur.execute(f"SELECT * FROM {table_name} {order_clause} LIMIT 50")
        rows_data = cur.fetchall()

        columns = [description[0] for description in cur.description] if cur.description else []
        rows = [dict(r) for r in rows_data]

        conn.close()

        return templates.TemplateResponse(
            "fragments/syspanel/db_explorer.html",
            {
                "request": request,
                "table_name": table_name,
                "columns": columns,
                "rows": rows
            }
        )
    except Exception as e:
        logger.error(f"DB Explorer Error: {e}")
        return _html_output(f'<div class="text-sm text-red-500">Query Error: {e}</div>')


@router.get("/fragments/gemini-cookies", response_class=HTMLResponse)
def frag_gemini_cookies(request: Request):
    cookie_path = os.path.join(APP_DIR, "gemini_cookies.json")
    invalid_flag = os.path.join(APP_DIR, "gemini_cookies_invalid")

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
            file_mtime = datetime.fromtimestamp(mtime, tz=ZoneInfo(TIMEZONE)).strftime("%H:%M:%S %d/%m/%Y")
            with open(cookie_path) as f:
                cookies = json.load(f)
            # Extract key cookies info
            KEY_NAMES = ["__Secure-1PSID", "__Secure-1PSIDTS", "__Secure-3PSID", "SID", "HSID", "SSID", "APISID", "SAPISID"]
            now_ts = time.time()
            for c in cookies:
                if c.get("name") in KEY_NAMES:
                    expiry = c.get("expiry", 0)
                    expired = expiry > 0 and expiry < now_ts
                    exp_str = datetime.fromtimestamp(expiry, tz=ZoneInfo(TIMEZONE)).strftime("%d/%m/%Y") if expiry else "session"
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


@router.get("/fragments/screenshots", response_class=HTMLResponse)
def frag_screenshots(request: Request):
    shots = _get_screenshots()
    # return paths relative for URL serving
    rel_shots = []
    for s in shots:
        rel = os.path.relpath(s, APP_DIR)
        name = os.path.basename(s)
        mtime = datetime.fromtimestamp(os.path.getmtime(s), tz=ZoneInfo(TIMEZONE))
        rel_shots.append({"path": s, "name": name, "mtime": mtime.strftime("%H:%M %d/%m")})
    return templates.TemplateResponse("fragments/syspanel/screenshots.html", {
        "request": request, "shots": rel_shots
    })


# ─── Log Viewer ──────────────────────────────────────────────────────────────

@router.get("/logs", response_class=HTMLResponse)
def get_logs(request: Request, worker: str = "Web_Dashboard", log_type: str = "error", lines: int = 100):
    # Bao gồm cả process names của root PM2 (production) và vu PM2 (dev)
    safe_workers = [
        "FB_Publisher", "AI_Generator", "Maintenance", "Web_Dashboard",       # vu PM2
        "ai-worker", "publisher", "maintenance", "web", "ai", "worker",        # root PM2
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
        for d in ["/home/vu/.pm2/logs", "/root/.pm2/logs"]:
            try:
                all_logs += [f"{d}/{f}" for f in os.listdir(d) if f.endswith(".log")]
            except Exception:
                all_logs.append(f"{d}: permission denied")
        content = (
            f"Log file not found or not readable: {log_file}\n\n"
            f"Available log files:\n" + "\n".join(f"  {x}" for x in all_logs)
        )
    escaped = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return HTMLResponse(f"<pre class='text-xs text-green-400 font-mono whitespace-pre-wrap leading-relaxed'>{escaped}</pre>")


# ─── Screenshot Serve ─────────────────────────────────────────────────────────

@router.get("/screenshot", response_class=HTMLResponse)
def serve_screenshot(path: str):
    """Serve a screenshot image by absolute path (security: must be within APP_DIR)."""
    abs_path = os.path.abspath(path)
    if not abs_path.startswith(APP_DIR):
        return HTMLResponse("Forbidden", status_code=403)
    if not os.path.exists(abs_path):
        return HTMLResponse("Not found", status_code=404)
    return FileResponse(abs_path)


# ─── Action Commands ──────────────────────────────────────────────────────────

@router.post("/cmd/git-pull", response_class=HTMLResponse)
def cmd_git_pull():
    out = run_cmd("git fetch origin && git reset --hard origin/develop")
    return _html_output(f"$ git fetch + reset --hard origin/develop\n\n{out}")


@router.post("/cmd/pm2-restart", response_class=HTMLResponse)
def cmd_pm2_restart():
    out = run_cmd("pm2 restart all")
    return _html_output(f"$ pm2 restart all\n\n{out}")


@router.post("/cmd/pm2-restart-one", response_class=HTMLResponse)
def cmd_pm2_restart_one(name: str = Form(...)):
    safe = ["FB_Publisher", "AI_Generator", "Maintenance", "Web_Dashboard"]
    if name not in safe:
        return _html_output(f"❌ Unknown process: {name}")
    out = run_cmd(f"pm2 restart {name}")
    return _html_output(f"$ pm2 restart {name}\n\n{out}")


@router.post("/cmd/pm2-start", response_class=HTMLResponse)
def cmd_pm2_start():
    out = run_cmd("bash start.sh")
    return _html_output(f"$ bash start.sh\n\n{out}")


@router.post("/cmd/pm2-stop", response_class=HTMLResponse)
def cmd_pm2_stop():
    out = run_cmd("pm2 delete all")
    return _html_output(f"$ pm2 delete all\n\n{out}")


@router.post("/cmd/kill-chrome", response_class=HTMLResponse)
def cmd_kill_chrome():
    chrome_out = run_cmd("pkill -f 'chrome' && echo 'Chrome killed' || echo 'No Chrome process found'")
    xvfb_out = run_cmd("pkill -f 'Xvfb' && echo 'Xvfb killed' || echo 'No Xvfb process found'")
    return _html_output(f"$ pkill chrome\n{chrome_out}\n\n$ pkill Xvfb\n{xvfb_out}")


@router.post("/cmd/start-vnc", response_class=HTMLResponse)
def cmd_start_vnc():
    # Kill existing to avoid port conflicts
    run_cmd("pkill -f x11vnc; pkill -f websockify")
    # Start x11vnc mapped to :99
    cmd_vnc = "nohup x11vnc -display :99 -nopw -listen localhost -xkb -ncache 10 -shared -forever -bg > vnc.log 2>&1 &"
    # Start websockify proxy
    cmd_web = "nohup websockify --web /usr/share/novnc/ 6080 localhost:5900 > web.log 2>&1 &"
    
    out1 = run_cmd(cmd_vnc)
    out2 = run_cmd(cmd_web)
    
    msg = f"✅ VNC Live Stream Started!\n\nNhớ mở SSH Tunnel trên máy bạn bằng lệnh sau:\n`ssh -L 6080:localhost:6080 root@14.225.218.116 -N`\n\nLink xem: http://localhost:6080/vnc.html\n\n[x11vnc]\n{out1}\n\n[websockify]\n{out2}"
    return _html_output(msg)


@router.post("/cmd/stop-vnc", response_class=HTMLResponse)
def cmd_stop_vnc():
    out_vnc = run_cmd("pkill -f x11vnc && echo 'x11vnc killed' || echo 'No x11vnc process found'")
    out_web = run_cmd("pkill -f websockify && echo 'websockify killed' || echo 'No websockify process found'")
    return _html_output(f"🛑 VNC Stream Stopped\n\n$ pkill x11vnc\n{out_vnc}\n\n$ pkill websockify\n{out_web}")


@router.post("/cmd/cleanup-db", response_class=HTMLResponse)
def cmd_cleanup_db():
    venv = "source venv/bin/activate && " if os.path.exists(os.path.join(APP_DIR, "venv")) else ""
    out = run_cmd(f"{venv}python scripts/fix_garbage_pages.py")
    return _html_output(f"$ python scripts/fix_garbage_pages.py\n\n{out}")


@router.post("/cmd/db-vacuum", response_class=HTMLResponse)
def cmd_db_vacuum():
    db_path = os.path.join(APP_DIR, "data/auto_publisher.db")
    before = os.path.getsize(db_path) / 1024**2 if os.path.exists(db_path) else 0
    out = run_cmd(f"sqlite3 '{db_path}' 'VACUUM;'")
    after = os.path.getsize(db_path) / 1024**2 if os.path.exists(db_path) else 0
    saved = before - after
    return _html_output(f"$ sqlite3 VACUUM\n\nBefore: {before:.2f} MB\nAfter:  {after:.2f} MB\nSaved:  {saved:.2f} MB\n\n{out}")


@router.post("/cmd/db-backup", response_class=HTMLResponse)
def cmd_db_backup():
    db_path = os.path.join(APP_DIR, "data/auto_publisher.db")
    backup_dir = os.path.join(APP_DIR, "data/backups")
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now(tz=ZoneInfo(TIMEZONE)).strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"auto_publisher_{ts}.db")
    try:
        shutil.copy2(db_path, backup_path)
        size = os.path.getsize(backup_path) / 1024**2
        return _html_output(f"✅ Backup created:\n{backup_path}\nSize: {size:.2f} MB")
    except Exception as e:
        return _html_output(f"❌ Backup failed: {e}")


@router.post("/cmd/cleanup-videos", response_class=HTMLResponse)
def cmd_cleanup_videos():
    """Delete media files for DONE jobs older than 7 days."""
    db = SessionLocal()
    cutoff = int(time.time()) - 7 * 86400
    try:
        done_jobs = db.query(Job).filter(
            Job.status == "DONE",
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


@router.post("/cmd/retry-failed", response_class=HTMLResponse)
def cmd_retry_failed():
    """Bulk retry all FAILED jobs."""
    db = SessionLocal()
    try:
        failed = db.query(Job).filter(Job.status == "FAILED").all()
        count = len(failed)
        for job in failed:
            job.status = "PENDING"
            job.tries = 0
            job.locked_at = None
        db.commit()
        return _html_output(f"✅ Retried {count} FAILED jobs → PENDING")
    except Exception as e:
        db.rollback()
        return _html_output(f"❌ Error: {e}")
    finally:
        db.close()


@router.post("/cmd/cancel-stuck", response_class=HTMLResponse)
def cmd_cancel_stuck():
    """Cancel RUNNING jobs that haven't had a heartbeat in 10 min."""
    db = SessionLocal()
    cutoff = int(time.time()) - 600
    try:
        stuck = db.query(Job).filter(
            Job.status == "RUNNING",
            Job.last_heartbeat_at < cutoff
        ).all()
        count = len(stuck)
        for job in stuck:
            job.status = "FAILED"
            job.last_error = "Cancelled: no heartbeat for 10+ min (manual syspanel)"
        db.commit()
        return _html_output(f"✅ Cancelled {count} stuck RUNNING jobs → FAILED")
    except Exception as e:
        db.rollback()
        return _html_output(f"❌ Error: {e}")
    finally:
        db.close()


@router.post("/cmd/clear-gemini-cookies", response_class=HTMLResponse)
def cmd_clear_gemini_cookies():
    """Delete Gemini cookie file and invalid flag."""
    cookie_path = os.path.join(APP_DIR, "gemini_cookies.json")
    invalid_flag = os.path.join(APP_DIR, "gemini_cookies_invalid")
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


# ─── Persona Tuner ────────────────────────────────────────────────────────────

PERSONA_FILE = os.path.join(APP_DIR, "ai_persona.json")
DEFAULT_PERSONA = (
    "Bạn là chuyên gia content sáng tạo, viết tiếng Việt tự nhiên, gần gũi với người dùng Facebook Việt Nam. "
    "Hãy viết caption hấp dẫn, giàu cảm xúc, phù hợp với chủ đề video, có thể dùng emoji vừa phải."
)


def _load_persona() -> str:
    try:
        if os.path.exists(PERSONA_FILE):
            with open(PERSONA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("system_prompt", DEFAULT_PERSONA)
    except Exception:
        pass
    return DEFAULT_PERSONA


@router.get("/persona", response_class=HTMLResponse)
def get_persona(request: Request):
    prompt = _load_persona()
    return templates.TemplateResponse("fragments/syspanel/persona_tuner.html", {
        "request": request,
        "prompt": prompt,
    })


@router.post("/persona", response_class=HTMLResponse)
def save_persona(system_prompt: str = Form("")):
    try:
        with open(PERSONA_FILE, "w", encoding="utf-8") as f:
            json.dump({"system_prompt": system_prompt.strip()}, f, ensure_ascii=False, indent=2)
        return _html_output("✅ Đã lưu Persona AI mới! Bot sẽ dùng giọng văn này từ job tiếp theo.")
    except Exception as e:
        return _html_output(f"❌ Lỗi: {e}")


