import os
import sys
import json
import subprocess
import logging
import time
import psutil
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import func, case, and_
from app.core.database.models import SystemState, Job, Account
from app.constants import AccountStatus, JobStatus
import app.config as config

logger = logging.getLogger(__name__)

_GEMINI_LOGIN_SCRIPT = Path("scripts") / "login_gemini_bypass.py"


# Đo phiên bản sinh một tiến trình con. `get_system_health` được gọi bởi trang web,
# `/health/json` và cả lệnh Telegram — nhớ tạm 5 phút là quá đủ vì phiên bản không đổi giữa
# hai lần khởi động (ADR-029 mục 4).
_YTDLP_PROBE_TTL_SEC = 300
_ytdlp_probe_cache: dict = {"at": 0.0, "value": None}


def _version_key(v: str) -> tuple:
    """So phiên bản theo SỐ, không theo chuỗi: `"2026.8.19" < "2026.3.3"` là sai khi so chuỗi."""
    return tuple(int(x) if x.isdigit() else 0 for x in str(v).split("."))


def _probe_ytdlp_binary() -> dict:
    """
    Chạy ``--version`` trên **chính argv mà ``yt_dlp_cmd`` sẽ dùng** (ADR-029 mục 2).

    Đây mới là sự thật về cái tool đang chạy. Đọc phiên bản **gói** bằng
    ``importlib.metadata`` chỉ nói lên bản trong venv — hai thứ có thể khác nhau, và ngày
    2026-09-09 đúng là khác nhau (binary trên PATH cũ 17 tháng).

    Không bao giờ ném: trang Sức khỏe không được chết vì một lượt đo phiên bản.
    """
    import subprocess
    import time as _time

    now = _time.time()
    cached = _ytdlp_probe_cache.get("value")
    if cached is not None and now - float(_ytdlp_probe_cache.get("at") or 0) < _YTDLP_PROBE_TTL_SEC:
        return cached

    result = {"binary": None, "version": None, "error": None}
    try:
        from app.core.yt_dlp_path import yt_dlp_cmd

        argv = yt_dlp_cmd("--version")
        result["binary"] = argv[0] if len(argv) == 1 else " ".join(str(a) for a in argv[:-1])
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=10)
        if proc.returncode == 0:
            result["version"] = (proc.stdout or "").strip() or None
        else:
            result["error"] = ((proc.stderr or "").strip() or f"exit {proc.returncode}")[:200]
    except Exception as exc:
        result["error"] = f"không chạy được yt-dlp: {exc}"[:200]

    _ytdlp_probe_cache["at"] = now
    _ytdlp_probe_cache["value"] = result
    return result


def _ytdlp_version_status() -> dict:
    """
    So phiên bản yt-dlp **đang thật sự chạy** với bản ghim trong ``requirements.txt``.

    Vì sao cần: TikTok/YouTube đổi cấu trúc liên tục, yt-dlp vá theo. Bản cũ gãy âm thầm —
    quét kênh trả "Unable to extract secondary user ID" mà không ai biết là do phần mềm cũ
    (đúng ca 2026-09-08 trên máy Owner). Chỉ ĐỌC, không tự cập nhật.

    ADR-029: ``installed`` nay là phiên bản của **binary tool gọi**, không phải của gói trong
    venv. ``package`` giữ số của gói để đối chiếu; lệch nhau (``mismatch``) nghĩa là có một
    bản yt-dlp lạ chen vào — chính cảnh báo này, nếu có từ trước, đã cắt ngắn buổi chẩn đoán
    2026-09-09 còn một phút.
    """
    info = {
        "installed": None, "pinned": None, "outdated": False, "error": None,
        "binary": None, "package": None, "mismatch": False,
    }
    try:
        from importlib.metadata import version as _pkg_version

        info["package"] = _pkg_version("yt-dlp")
    except Exception as exc:
        info["error"] = f"không đọc được phiên bản gói: {exc}"

    probe = _probe_ytdlp_binary()
    info["binary"] = probe.get("binary")
    info["installed"] = probe.get("version") or info["package"]
    if probe.get("error") and not info["error"]:
        info["error"] = probe["error"]
    # Tính NGAY tại đây, trước lượt đọc `requirements.txt`: đường đó có `return` sớm khi đọc
    # hỏng, mà cảnh báo "có yt-dlp lạ chen vào" lại là thứ đáng giá nhất — không được biến mất
    # chỉ vì một thứ khác cũng hỏng.
    if info["package"] and probe.get("version"):
        info["mismatch"] = _version_key(probe["version"]) != _version_key(info["package"])

    if not info["installed"]:
        info["error"] = info["error"] or "không đọc được phiên bản đang chạy"
        return info
    try:
        import re as _re

        req = Path(__file__).resolve().parents[3] / "requirements.txt"
        for line in req.read_text(encoding="utf-8", errors="replace").splitlines():
            m = _re.match(r"^\s*yt-dlp\s*==\s*([0-9][^\s#]*)", line)
            if m:
                info["pinned"] = m.group(1)
                break
    except Exception as exc:
        info["error"] = f"không đọc được requirements.txt: {exc}"
        return info

    if info["pinned"] and info["installed"]:
        info["outdated"] = _version_key(info["installed"]) < _version_key(info["pinned"])
    return info


class HealthService:
    @staticmethod
    def get_gemini_health() -> dict:
        cookie_path = str(config.GEMINI_COOKIES_FILE)
        invalid_flag = str(config.GEMINI_COOKIES_INVALID_FLAG)
        
        is_valid = False
        if os.path.exists(invalid_flag):
            is_valid = False
        elif os.path.exists(cookie_path):
            try:
                with open(cookie_path, "r") as f:
                    cookies = json.load(f)
                for c in cookies:
                    if c.get("name") == "__Secure-1PSID":
                        expiry = c.get("expiry", 0)
                        if expiry > time.time():
                            is_valid = True
                        break
            except Exception as e:
                logger.error("Error reading cookies: %s", e)
        return {"is_valid": is_valid}

    @staticmethod
    def start_gemini_login():
        """Spawn Gemini cookie login in a detached process (visible Chrome)."""
        script = (config.BASE_DIR / _GEMINI_LOGIN_SCRIPT).resolve()
        if not script.is_file():
            raise FileNotFoundError(f"Missing Gemini login script: {script}")
        python_bin = sys.executable
        if not python_bin or not Path(python_bin).exists():
            raise FileNotFoundError(f"Python executable not found: {python_bin!r}")

        env = os.environ.copy()
        # Xvfb display is Linux-only; do not force it on Windows local runs.
        if os.name != "nt":
            env["DISPLAY"] = env.get("DISPLAY") or ":99"

        logger.info("Launching Gemini login: %s %s", python_bin, script)
        subprocess.Popen(
            [python_bin, str(script)],
            env=env,
            cwd=str(config.BASE_DIR),
            start_new_session=True,
        )

    @staticmethod
    def get_system_health(db: Session, orphan_threshold_seconds: int = 300) -> dict:
        """
        Executes fast indexed count aggregations to evaluate system health.
        Avoids full table fetches.
        
        Phase C upgrade:
          - Per-account 7-day rolling success rate (single aggregated SQL)
          - Worker uptime tracking
          - Metrics summary (views, clicks)
        """
        now = int(time.time())
        
        # 1. Worker State (Fast 1-row fetch)
        sys_state = db.query(SystemState).filter(SystemState.id == 1).first()
        worker_status = sys_state.worker_status if sys_state else "UNKNOWN"
        worker_hb = sys_state.heartbeat_at if sys_state else 0
        safe_mode = sys_state.safe_mode if sys_state else False
        worker_hb_age = now - worker_hb if worker_hb else 999999
        worker_started = sys_state.worker_started_at if sys_state else None
        uptime_seconds = (now - worker_started) if worker_started else 0
        
        # 2. Job Counters (Indexed)
        running_jobs_count = db.query(Job).filter(Job.status == JobStatus.RUNNING).count()
        orphan_jobs_count = db.query(Job).filter(
            Job.status == JobStatus.RUNNING,
            Job.last_heartbeat_at < (now - orphan_threshold_seconds)
        ).count()
        
        failed_last_24h = db.query(Job).filter(
            Job.status == JobStatus.FAILED,
            Job.finished_at >= (now - 86400)
        ).count()
        
        # 3. Account Breaker Counters (Indexed)
        disabled_accounts_count = db.query(Account).filter(
            (Account.is_active == False) | (Account.login_status != AccountStatus.ACTIVE)
        ).count()
        
        # 4. Psutil Metrics
        try:
            process = psutil.Process()
            memory_usage_mb = process.memory_info().rss / 1024 / 1024
            
            # System wide metrics
            cpu_percent = psutil.cpu_percent(interval=None)
            vm = psutil.virtual_memory()
            sys_memory_percent = vm.percent
            sys_memory_total_gb = vm.total / (1024**3)
            sys_memory_used_gb = vm.used / (1024**3)
            
            disk = psutil.disk_usage('/')
            disk_percent = disk.percent
            disk_total_gb = disk.total / (1024**3)
            disk_used_gb = disk.used / (1024**3)

            browser_process_count = sum(
                1 for p in psutil.process_iter(['name']) 
                if "playwright" in p.info.get('name', '').lower() or "chrome" in p.info.get('name', '').lower()
            )
        except Exception:
            memory_usage_mb = 0
            browser_process_count = 0
            cpu_percent = 0
            sys_memory_percent = 0
            sys_memory_total_gb = 0
            sys_memory_used_gb = 0
            disk_percent = 0
            disk_total_gb = 0
            disk_used_gb = 0

        # 5. Per-Account Health — 7-day rolling (SINGLE aggregated SQL, no N+1)
        seven_days_ago = now - 604800
        
        account_stats_raw = (
            db.query(
                Account.id,
                Account.name,
                Account.platform,
                Account.is_active,
                Account.login_status,
                Account.consecutive_fatal_failures,
                func.count(case((and_(Job.status == JobStatus.DONE, Job.finished_at >= seven_days_ago), 1))).label("done_7d"),
                func.count(case((and_(Job.status == JobStatus.FAILED, Job.finished_at >= seven_days_ago), 1))).label("failed_7d"),
            )
            .outerjoin(Job, and_(Job.account_id == Account.id, Job.finished_at >= seven_days_ago))
            .group_by(Account.id)
            .all()
        )
        
        account_stats = []
        for row in account_stats_raw:
            total = row.done_7d + row.failed_7d
            success_rate = round(row.done_7d / total * 100, 1) if total > 0 else 0
            account_stats.append({
                "id": row.id,
                "name": row.name,
                "platform": row.platform,
                "is_active": row.is_active,
                "login_status": row.login_status,
                "done_7d": row.done_7d,
                "failed_7d": row.failed_7d,
                "success_rate": success_rate,
                "circuit_breaker": row.consecutive_fatal_failures,
            })
        
        # 6. Metrics Overview (Phase 14+15 data)
        total_views = db.query(func.sum(Job.view_24h)).filter(Job.view_24h != None).scalar() or 0
        total_clicks = db.query(func.sum(Job.click_count)).filter(Job.click_count != None, Job.click_count > 0).scalar() or 0
        avg_views = db.query(func.avg(Job.view_24h)).filter(Job.view_24h != None).scalar() or 0
        
        posts_with_metrics = db.query(Job).filter(Job.metrics_checked == True).count()

        # === DETERMINISTIC DEGRADATION LOGIC ===
        status = "ok"
        degradation_reasons = []

        if worker_status != JobStatus.RUNNING:
            status = "degraded"
            degradation_reasons.append(f"Worker is {worker_status}")
            
        if worker_hb_age > 120 and worker_status == JobStatus.RUNNING: # 2 minutes dead
            status = "degraded"
            degradation_reasons.append(f"Worker heartbeat stale ({worker_hb_age}s)")

        if orphan_jobs_count > 0:
            status = "degraded"
            degradation_reasons.append(f"Detected {orphan_jobs_count} orphan jobs")

        if failed_last_24h > 10:
            status = "degraded"
            degradation_reasons.append(f"High failure rate ({failed_last_24h} in 24h)")
            
        if disabled_accounts_count > 0:
            status = "degraded"
            degradation_reasons.append(f"{disabled_accounts_count} accounts are disabled or invalid")

        ytdlp = _ytdlp_version_status()
        if ytdlp.get("outdated"):
            status = "degraded"
            degradation_reasons.append(
                f"yt-dlp cũ ({ytdlp['installed']} < {ytdlp['pinned']}) — quét kênh/tải video có thể gãy. "
                r"Chạy: venv\Scripts\python.exe -m pip install -r requirements.txt"
            )
        if ytdlp.get("mismatch"):
            status = "degraded"
            degradation_reasons.append(
                f"yt-dlp đang chạy ({ytdlp['installed']}) khác bản trong venv ({ytdlp['package']}) — "
                f"tool gọi {ytdlp.get('binary')}. Có một bản yt-dlp lạ chen vào."
            )

        return {
            "status": status,
            "reasons": degradation_reasons,
            "ytdlp": ytdlp,
            "worker": {
                "status": worker_status,
                "heartbeat_age_seconds": worker_hb_age,
                "safe_mode": safe_mode,
                "uptime_seconds": uptime_seconds,
                "uptime_hours": round(uptime_seconds / 3600, 1),
            },
            "jobs": {
                "running": running_jobs_count,
                "orphans": orphan_jobs_count,
                "failed_24h": failed_last_24h
            },
            "accounts": {
                "disabled_or_invalid": disabled_accounts_count,
                "details": account_stats,
            },
            "metrics": {
                "total_views": total_views,
                "total_clicks": total_clicks,
                "avg_views_per_post": round(avg_views, 1),
                "posts_checked": posts_with_metrics,
            },
            "system": {
                "memory_mb": round(memory_usage_mb, 2),
                "browser_processes": browser_process_count,
                "cpu_percent": round(cpu_percent, 1),
                "sys_memory_percent": round(sys_memory_percent, 1),
                "sys_memory_total_gb": round(sys_memory_total_gb, 1),
                "sys_memory_used_gb": round(sys_memory_used_gb, 1),
                "disk_percent": round(disk_percent, 1),
                "disk_total_gb": round(disk_total_gb, 1),
                "disk_used_gb": round(disk_used_gb, 1),
            }
        }
    @staticmethod
    def notify_worker_down():
        from app.core.notifier.service import NotifierService
        NotifierService.notify_worker_down()

    @staticmethod
    def sync_cookies(cookies: list):
        cookie_path = str(config.GEMINI_COOKIES_FILE)
        invalid_flag = str(config.GEMINI_COOKIES_INVALID_FLAG)
        with open(cookie_path, "w") as f:
            json.dump(cookies, f)
        if os.path.exists(invalid_flag):
            os.remove(invalid_flag)
