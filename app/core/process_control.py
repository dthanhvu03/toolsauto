"""
Bảng tiến trình PM2 cho web (PLAN-115): đọc trạng thái + bật / tắt / khởi động lại đúng các app trong danh sách.

Chỉ tên trong ``PM2_SAFE_NAMES`` và hành động ``start / stop / restart``. Lệnh chạy **tách khỏi web** (``setsid -f``) rồi
``pm2 save`` (máy khởi động lại vẫn giữ app nào bật / tắt), web trả lời ngay — vì:
- khởi động lại ``Web_Dashboard`` từ chính nó: PM2 giết web (cả cây tiến trình con) giữa chừng;
- tắt ``Studio_Heavy`` chờ tới 15 phút cho bản render dở xong (``kill_timeout``).
Bảng trên web tự hỏi lại vài giây một lần nên thấy kết quả ngay sau đó.
"""
from __future__ import annotations

import json
import logging
import shlex
import shutil
import subprocess
import time

import psutil

from app.core.pm2_apps import APP_INFO, PM2_SAFE_NAMES, SYSTEMD_SERVICES

logger = logging.getLogger(__name__)

ACTIONS = ("start", "stop", "restart")
PM2_TIMEOUT_SEC = 30


class ProcessError(ValueError):
    """Thông điệp đưa thẳng cho người dùng."""


def _pm2(*args: str, timeout: int = PM2_TIMEOUT_SEC) -> subprocess.CompletedProcess:
    exe = shutil.which("pm2")
    if not exe:
        raise ProcessError("không tìm thấy lệnh pm2 trên máy này")
    return subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout)


def _spawn(script: str) -> None:
    """Chạy ``sh -c script`` tách hẳn khỏi web (``setsid -f``: tiến trình con không thuộc cây của web)."""
    subprocess.run(["setsid", "-f", "sh", "-c", script], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=10, check=True)


def _gpu() -> dict | None:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "--query-gpu=name,memory.used,memory.total,utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip().splitlines()[0]
        name, used, total, util = [x.strip() for x in out.split(",")]
        return {"name": name, "mem_used_mb": int(used), "mem_total_mb": int(total), "util_pct": int(util)}
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def _app(p: dict, now: float) -> dict:
    env = p.get("pm2_env") or {}
    name = p.get("name") or ""
    info = APP_INFO.get(name, {})
    status = env.get("status") or "unknown"
    started = env.get("pm_uptime")
    known = name in PM2_SAFE_NAMES
    return {
        "name": name, "label": info.get("label") or name, "role": info.get("role") or "",
        "if_stopped": info.get("if_stopped") or "", "status": status,
        "cpu": (p.get("monit") or {}).get("cpu") or 0,
        "mem_mb": round(((p.get("monit") or {}).get("memory") or 0) / 1048576),
        "uptime_s": int(now - started / 1000) if started and status == "online" else None,
        "restarts": env.get("restart_time") or 0, "pid": p.get("pid") or None,
        "can_start": known and status != "online",
        "can_stop": known and status == "online" and info.get("can_stop", True),
        "can_restart": known and status == "online",
    }


_SYSTEMD_STATUS = {"active": "online", "inactive": "stopped", "failed": "errored",
                   "activating": "launching", "deactivating": "stopping", "reloading": "online"}
_SYSTEMD_PROPS = "Id,ActiveState,SubState,MainPID,NRestarts,MemoryCurrent"
# Giữ psutil.Process giữa các lần hỏi để cpu_percent() đo được (lần đầu luôn 0).
_proc_cache: dict[int, psutil.Process] = {}


def _systemctl_show(units: list[str]) -> list[dict[str, str]]:
    exe = shutil.which("systemctl")
    if not exe:
        raise ProcessError("không có systemctl trên máy này")
    out = subprocess.run([exe, "show", "--no-pager", "-p", _SYSTEMD_PROPS, *units],
                         capture_output=True, text=True, timeout=10).stdout
    blocks: list[dict[str, str]] = []
    for chunk in out.strip().split("\n\n"):
        row = dict(line.split("=", 1) for line in chunk.splitlines() if "=" in line)
        if row:
            blocks.append(row)
    return blocks


def _service(row: dict[str, str], now: float) -> dict:
    unit = row.get("Id", "").removesuffix(".service")
    info = SYSTEMD_SERVICES.get(unit, {})
    status = _SYSTEMD_STATUS.get(row.get("ActiveState", ""), row.get("ActiveState") or "unknown")
    pid = int(row.get("MainPID") or 0) or None
    cpu, mem_mb, uptime = 0.0, 0, None
    mem_raw = row.get("MemoryCurrent", "")
    if mem_raw.isdigit():
        mem_mb = round(int(mem_raw) / 1048576)
    if pid and status == "online":
        try:
            proc = _proc_cache.get(pid) or _proc_cache.setdefault(pid, psutil.Process(pid))
            cpu = round(proc.cpu_percent(interval=None), 1)
            uptime = int(now - proc.create_time())
            if not mem_mb:
                mem_mb = round(proc.memory_info().rss / 1048576)
        except (psutil.Error, OSError):
            _proc_cache.pop(pid, None)
    return {
        "name": unit, "label": info.get("label") or unit, "role": info.get("role") or "",
        "group": info.get("group") or "", "manage": info.get("manage") or f"systemctl restart {unit}",
        "if_stopped": "", "status": status, "cpu": cpu, "mem_mb": mem_mb, "uptime_s": uptime,
        "restarts": int(row.get("NRestarts") or 0), "pid": pid,
        "can_start": False, "can_stop": False, "can_restart": False,
    }


def services(now: float | None = None) -> tuple[list[dict], str | None]:
    """Bot chạy bằng systemd (cashback, AI Pass Store) — chỉ đọc."""
    now = time.time() if now is None else now
    units = [f"{u}.service" for u in SYSTEMD_SERVICES]
    try:
        rows = _systemctl_show(units)
    except (ProcessError, OSError, subprocess.SubprocessError) as exc:
        return [], f"không đọc được systemd: {exc}"
    return [_service(r, now) for r in rows], None


def snapshot(now: float | None = None) -> dict:
    """Mọi app PM2 + RAM / CPU máy + GPU. pm2 hỏng thì ``apps=[]`` kèm ``error`` (trang vẫn hiện phần máy)."""
    now = time.time() if now is None else now
    mem = psutil.virtual_memory()
    out: dict = {
        "machine": {
            "cpu_pct": psutil.cpu_percent(interval=0.1), "cpus": psutil.cpu_count() or 0,
            "mem_total_mb": round(mem.total / 1048576), "mem_used_mb": round((mem.total - mem.available) / 1048576),
            "gpu": _gpu(),
        },
        "apps": [], "error": None,
    }
    out["services"], out["services_error"] = services(now)
    try:
        proc = _pm2("jlist")
        apps = json.loads(proc.stdout or "[]")
    except (ProcessError, OSError, subprocess.SubprocessError, ValueError) as exc:
        out["error"] = f"không đọc được PM2: {exc}"
        return out
    rows = [_app(p, now) for p in apps if isinstance(p, dict)]
    out["apps"] = sorted(rows, key=lambda a: (a["status"] != "online", -a["mem_mb"], a["name"]))
    return out


def act(name: str, action: str) -> str:
    """Gửi ``pm2 <action> <name>; pm2 save`` (tách khỏi web). Sai tên / hành động / bị chặn → ``ProcessError``."""
    if name not in PM2_SAFE_NAMES:
        raise ProcessError(f"không điều khiển app «{name}» từ web")
    if action not in ACTIONS:
        raise ProcessError(f"không có hành động «{action}»")
    if action == "stop" and not APP_INFO.get(name, {}).get("can_stop", True):
        raise ProcessError(f"không tắt {name} từ web — chỉ khởi động lại được")
    exe = shutil.which("pm2")
    if not exe:
        raise ProcessError("không tìm thấy lệnh pm2 trên máy này")
    pm2 = shlex.quote(exe)
    try:
        _spawn(f"{pm2} {action} {shlex.quote(name)}; {pm2} save")
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProcessError(f"không gửi được lệnh: {exc}") from exc
    logger.info("[PROCESS] gửi pm2 %s %s", action, name)
    label = APP_INFO.get(name, {}).get("label") or name
    if name == "Web_Dashboard":
        return "Đang khởi động lại web — trang mất kết nối vài giây rồi tự có lại."
    if action == "stop" and name == "Studio_Heavy":
        return f"Đang tắt {label} — nếu đang render thì chờ bản đó xong mới dừng."
    return {"start": "Đang bật", "stop": "Đang tắt", "restart": "Đang khởi động lại"}[action] + f" {label}…"
