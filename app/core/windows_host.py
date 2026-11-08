"""
Máy Windows chứa WSL — RAM / CPU / ổ đĩa / chương trình tốn tài nguyên nhất, cho «Panel hệ thống». Chỉ đọc.

Gọi ``powershell.exe`` từ WSL (≈ 2,5 giây / lần) nên kết quả giữ ``CACHE_SEC`` giây cho mọi người xem chung.
% CPU từng chương trình = chênh lệch thời gian CPU giữa 2 lần đọc (lần đầu chưa có → ``None``).
Không chạy trong WSL (không thấy powershell.exe) → ``available=False``, trang vẫn hiện phần còn lại.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_SEC = 8
PS_TIMEOUT_SEC = 20
TOP_N = 10
_PS_FALLBACK = Path("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")

# Mỗi chương trình: [tên, working set (byte), tổng thời gian CPU (giây)] — mảng phẳng cho JSON gọn.
_SCRIPT = r"""
$os=Get-CimInstance Win32_OperatingSystem; $cpu=Get-CimInstance Win32_Processor;
$d=Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3"|%{@($_.DeviceID,$_.VolumeName,[int64]$_.Size,[int64]$_.FreeSpace)};
$p=Get-Process|%{@($_.ProcessName,[int64]$_.WorkingSet64,[double]$_.TotalProcessorTime.TotalSeconds)};
@{t=[int64]$os.TotalVisibleMemorySize;f=[int64]$os.FreePhysicalMemory;c=($cpu|Measure LoadPercentage -Average).Average;
n=$cpu[0].Name;k=($cpu|Measure NumberOfLogicalProcessors -Sum).Sum;b=$os.LastBootUpTime.ToString("o");d=$d;p=$p}|ConvertTo-Json -Compress
"""

# Tên tiến trình Windows → tên dễ hiểu (khớp không phân biệt hoa thường)
LABELS = {
    "vmmemwsl": "WSL (cả ToolsAuto, bot, Postgres…)",
    "vmmem": "WSL / máy ảo",
    "memory compression": "Windows nén RAM",
    "msmpeng": "Windows Defender",
    "chrome": "Chrome",
    "msedge": "Edge",
    "cursor": "Cursor",
    "code": "VS Code",
    "explorer": "Windows Explorer",
    "svchost": "Dịch vụ Windows (svchost)",
    "powershell": "PowerShell (gồm lượt web đọc số liệu này)",
    "dwm": "Hiển thị Windows (dwm)",
    "ultraviewer_desktop": "UltraViewer",
    "tailscaled": "Tailscale",
    "googledrivefs": "Google Drive",
    "ollama": "Ollama",
    "docker desktop": "Docker Desktop",
}
_SKIP = {"idle", "_total"}

_lock = threading.Lock()
_cache: dict | None = None
_cache_at = 0.0
_prev_cpu: dict[str, float] = {}
_prev_at = 0.0


def _powershell() -> str | None:
    exe = shutil.which("powershell.exe")
    if exe:
        return exe
    return str(_PS_FALLBACK) if _PS_FALLBACK.exists() else None


def _query(exe: str) -> dict:
    proc = subprocess.run(
        [exe, "-NoProfile", "-NonInteractive", "-Command", _SCRIPT],
        capture_output=True, text=True, timeout=PS_TIMEOUT_SEC, stdin=subprocess.DEVNULL,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError((proc.stderr or "powershell không trả dữ liệu").strip()[:200])
    return json.loads(proc.stdout)


def _chunks(flat: list | None, size: int) -> list[list]:
    flat = flat or []
    return [flat[i:i + size] for i in range(0, len(flat) - size + 1, size)]


def _label(name: str) -> str:
    return LABELS.get(name.lower(), name)


def _group(procs: list[list], prev: dict[str, float], elapsed: float, cpus: int) -> tuple[list[dict], dict[str, float]]:
    """Gộp theo tên (Chrome 30 tiến trình → 1 dòng). % CPU tính trên cả máy (100% = mọi nhân)."""
    groups: dict[str, dict] = {}
    for name, ws, cpu_s in procs:
        key = re.sub(r"#\d+$", "", str(name))
        if key.lower() in _SKIP:
            continue
        g = groups.setdefault(key, {"name": key, "label": _label(key), "count": 0, "mem_bytes": 0, "cpu_s": 0.0})
        g["count"] += 1
        g["mem_bytes"] += int(ws or 0)
        g["cpu_s"] += float(cpu_s or 0)
    totals = {k: g["cpu_s"] for k, g in groups.items()}
    rows = []
    for key, g in groups.items():
        cpu_pct = None
        if prev and elapsed > 0 and key in prev and cpus:
            cpu_pct = round(max(0.0, g["cpu_s"] - prev[key]) / (elapsed * cpus) * 100, 1)
        rows.append({"name": key, "label": g["label"], "count": g["count"],
                     "mem_mb": round(g["mem_bytes"] / 1048576), "cpu_pct": cpu_pct})
    rows.sort(key=lambda r: -r["mem_mb"])
    return rows, totals


def build(raw: dict, prev: dict[str, float], elapsed: float, now: float) -> tuple[dict, dict[str, float]]:
    """Dữ liệu powershell → JSON cho web (tách riêng để test không cần Windows)."""
    cpus = int(raw.get("k") or 0)
    total_kb, free_kb = int(raw.get("t") or 0), int(raw.get("f") or 0)
    disks = []
    for drive, label, size, free in _chunks(raw.get("d"), 4):
        size, free = int(size or 0), int(free or 0)
        if size <= 0:
            continue
        disks.append({"drive": drive, "label": label if label and label != "?" else "",
                      "total_gb": round(size / 1e9, 1), "used_gb": round((size - free) / 1e9, 1),
                      "free_gb": round(free / 1e9, 1)})
    rows, totals = _group(_chunks(raw.get("p"), 3), prev, elapsed, cpus)
    try:
        uptime_s = max(0, int(now - datetime.fromisoformat(str(raw.get("b"))).timestamp()))
    except (TypeError, ValueError):
        uptime_s = None
    wsl = next((r for r in rows if r["name"].lower() in ("vmmemwsl", "vmmem")), None)
    return {
        "available": True, "error": None,
        "cpu_pct": float(raw.get("c") or 0), "cpu_name": str(raw.get("n") or "").strip(), "cpus": cpus,
        "mem_total_mb": round(total_kb / 1024), "mem_used_mb": round((total_kb - free_kb) / 1024),
        "uptime_s": uptime_s, "disks": disks, "wsl_mem_mb": wsl["mem_mb"] if wsl else None,
        "top": rows[:TOP_N], "process_count": sum(r["count"] for r in rows),
    }, totals


def snapshot(now: float | None = None) -> dict:
    """Số liệu Windows (giữ ``CACHE_SEC`` giây). Lỗi → ``available``/``error`` — không bao giờ raise."""
    global _cache, _cache_at, _prev_cpu, _prev_at
    with _lock:
        now = time.time() if now is None else now
        if _cache is not None and now - _cache_at < CACHE_SEC:
            return {**_cache, "age_s": round(now - _cache_at)}
        exe = _powershell()
        if not exe:
            return {"available": False, "error": "Không thấy powershell.exe — web không chạy trong WSL.", "age_s": 0}
        try:
            raw = _query(exe)
            data, totals = build(raw, _prev_cpu, now - _prev_at, now)
        except (OSError, subprocess.SubprocessError, RuntimeError, ValueError) as exc:
            logger.warning("windows_host: %s", exc)
            return {"available": False, "error": f"Không đọc được số liệu Windows: {exc}", "age_s": 0}
        _prev_cpu, _prev_at = totals, now
        _cache, _cache_at = data, now
        return {**data, "age_s": 0}
