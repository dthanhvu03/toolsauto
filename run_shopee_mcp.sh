#!/usr/bin/env bash
set -euo pipefail
# Shortlink bridge. PM2 kills WSL bash/node but Windows chrome.exe / node.exe often
# survive, so the next start hits "open in the current browser session" and 500s.

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PROFILE_WSL="/mnt/c/Users/Admin/.shopee-mcp/chrome-profile"
PROFILE_WIN='C:\Users\Admin\.shopee-mcp\chrome-profile'
NODE="/mnt/c/Program Files/nvm/nodejs/node.exe"
SCRIPT='C:\Users\Admin\AppData\Roaming\npm\node_modules\@bintangtimurlangit\shopee-mcp\build\index.js'
PS="/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"

mark_chrome_clean() {
  python3 - "$PROFILE_WSL" <<'PY'
from pathlib import Path
import json, sys
root = Path(sys.argv[1])
for rel in ("Local State", "Default/Preferences"):
    p = root / rel
    if not p.exists():
        continue
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        continue
    if not isinstance(data, dict):
        continue
    data["exited_cleanly"] = True
    data["exit_type"] = "Normal"
    profile = data.get("profile")
    if isinstance(profile, dict):
        profile["exited_cleanly"] = True
        profile["exit_type"] = "Normal"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
PY
}

kill_stale() {
  local pid
  pid="$(/mnt/c/Windows/System32/netstat.exe -ano 2>/dev/null | awk '/:9224/ && /LISTENING/ {print $NF; exit}' | tr -d '\r')"
  if [[ -n "${pid:-}" && "$pid" != "0" ]]; then
    /mnt/c/Windows/System32/taskkill.exe /PID "$pid" >/dev/null 2>&1 || true
    sleep 2
    /mnt/c/Windows/System32/taskkill.exe /F /PID "$pid" >/dev/null 2>&1 || true
  fi
  if [[ -x "$PS" ]]; then
    timeout 5 "$PS" -NoProfile -NonInteractive -Command \
      'Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path -like "*cloakbrowser*" } | Stop-Process -Force -ErrorAction SilentlyContinue' \
      >/dev/null 2>&1 || true
  fi
  rm -f "$PROFILE_WSL/lockfile" \
        "$PROFILE_WSL/SingletonLock" \
        "$PROFILE_WSL/SingletonSocket" \
        "$PROFILE_WSL/SingletonCookie" 2>/dev/null || true
  mark_chrome_clean
}

kill_stale
trap kill_stale EXIT INT TERM

export USERPROFILE='C:\Users\Admin'
export HOMEDRIVE='C:'
export HOMEPATH='\Users\Admin'
export SHOPEE_PROFILE_DIR="$PROFILE_WIN"
export SHOPEE_DOMAIN='shopee.vn'

# MCP stdio exits on EOF; PM2 does not keep stdin open.
sleep infinity | "$NODE" "$SCRIPT"
