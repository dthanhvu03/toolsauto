import subprocess
import os
import sys
import re
import time

def run(cmd):
    print(f"Running: {cmd}")
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def main():
    print("=== VNC Auto-Starter for VPS ===")
    
    # 1. Find Xvfb processes
    ps = run("ps aux | grep Xvfb | grep -v grep")
    if not ps.stdout.strip():
        print("Error: No Xvfb process found. Please start the publisher first.")
        return

    # Try to find display and auth
    # Improved regex to specifically look for Xvfb followed by display
    match = re.search(r"Xvfb\s+(:\d+).*?-auth\s+(\S+)", ps.stdout)
    if not match:
        # Fallback: just try to find display after Xvfb
        match_display = re.search(r"Xvfb\s+(:\d+)", ps.stdout)
        if not match_display:
            print("Error: Could not determine Xvfb display.")
            return
        display = match_display.group(1)
        auth = None
    else:
        display = match.group(1)
        auth = match.group(2)

    print(f"Detected Display: {display}")
    if auth:
        print(f"Detected Auth: {auth}")
    
    # 2. Kill old VNC/websockify
    print("Cleaning up old VNC/websockify processes...")
    run("pkill -f x11vnc")
    run("pkill -f websockify")
    time.sleep(1)

    # 3. Start x11vnc
    print(f"Starting x11vnc on {display}...")
    # STRATEGY: COMPLETELY UNSET WAYLAND TO AVOID CONFLICTS
    vnc_env = os.environ.copy()
    if "WAYLAND_DISPLAY" in vnc_env:
        del vnc_env["WAYLAND_DISPLAY"]
    vnc_env["XDG_SESSION_TYPE"] = "x11"
    
    vnc_cmd = f"nohup x11vnc -display {display} "
    if auth:
        vnc_cmd += f"-auth {auth} "
        vnc_env["XAUTHORITY"] = auth
    
    vnc_env["DISPLAY"] = display
    vnc_cmd += "-forever -shared -bg -rfbport 5900 -nopw -noxrecord -noxfixes -noxdamage > x11vnc.log 2>&1"
    
    print(f"Executing: {vnc_cmd}")
    subprocess.Popen(vnc_cmd, shell=True, env=vnc_env)
    time.sleep(1)

    # 3b. Start openbox window manager so windows appear properly
    wm_running = run("pgrep -x openbox")
    if not wm_running.stdout.strip():
        print(f"Starting openbox window manager on {display}...")
        wm_env = vnc_env.copy()
        wm_env["DISPLAY"] = display
        if auth:
            wm_env["XAUTHORITY"] = auth
        subprocess.Popen(
            "nohup openbox --replace > /tmp/openbox.log 2>&1",
            shell=True, env=wm_env
        )
        time.sleep(1)
    else:
        print(f"openbox already running (pid {wm_running.stdout.strip()})")

    # 4. Start websockify
    # Use common paths for novnc
    novnc_paths = ["/usr/share/novnc/", "/usr/local/share/novnc/"]
    web_path = next((p for p in novnc_paths if os.path.exists(p)), "/usr/share/novnc/")
    
    # Use 6080 (standard for noVNC) or 8080. Using 6080 to avoid sudo requirements.
    port = 6080
    # Use 127.0.0.1 instead of localhost for stability
    ws_cmd = f"nohup websockify --web {web_path} {port} 127.0.0.1:5900 > websockify.log 2>&1 &"
    print(f"Starting websockify on port {port} targeting 127.0.0.1:5900...")
    run(ws_cmd)
    
    time.sleep(2)
    
    # 5. Verify
    ports = run("ss -tlnp | grep -E '5900|80 '")
    print("\nStatus:")
    if "5900" in ports.stdout:
        print("[OK] x11vnc is listening on 5900")
    else:
        print("[FAIL] x11vnc is NOT listening (check x11vnc.log)")
        
    if f":{port} " in ports.stdout:
        print(f"[OK] websockify is listening on {port}")
    else:
        print(f"[FAIL] websockify is NOT listening (check websockify.log)")

    print(f"\nIf both are OK, open: http://<vps-ip>/vnc.html")

if __name__ == "__main__":
    main()
