import subprocess
import os
import sys
import re
import time

DEFAULT_DISPLAY = ":99"

def run(cmd):
    print(f"Running: {cmd}")
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def start_detached(args, env, log_path):
    print(f"Executing: {' '.join(args)}")
    log_file = open(log_path, "ab")
    return subprocess.Popen(
        args,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        env=env,
        start_new_session=True,
    )

def ensure_xvfb():
    ps = run("ps aux | grep Xvfb | grep -v grep")
    if ps.stdout.strip():
        return ps.stdout

    print(f"No Xvfb process found. Starting Xvfb {DEFAULT_DISPLAY}...")
    start_detached(
        [
            "Xvfb",
            DEFAULT_DISPLAY,
            "-screen",
            "0",
            "1280x720x24",
            "-ac",
            "+extension",
            "GLX",
            "+render",
            "-noreset",
        ],
        os.environ.copy(),
        "/tmp/xvfb-toolsauto.log",
    )
    time.sleep(2)

    ps = run("ps aux | grep Xvfb | grep -v grep")
    if not ps.stdout.strip():
        print("Error: Failed to start Xvfb. Check /tmp/xvfb-toolsauto.log")
    return ps.stdout

def main():
    print("=== VNC Auto-Starter for VPS ===")
    
    # 1. Find Xvfb processes
    xvfb_processes = ensure_xvfb()
    if not xvfb_processes.strip():
        return

    # Try to find display and auth
    # Improved regex to specifically look for Xvfb followed by display
    match = re.search(r"Xvfb\s+(:\d+).*?-auth\s+(\S+)", xvfb_processes)
    if not match:
        # Fallback: just try to find display after Xvfb
        match_display = re.search(r"Xvfb\s+(:\d+)", xvfb_processes)
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
    
    vnc_args = ["x11vnc", "-display", display]
    if auth:
        vnc_env["XAUTHORITY"] = auth
    
    vnc_env["DISPLAY"] = display
    vnc_args.extend([
        "-forever",
        "-shared",
        "-rfbport",
        "5900",
        "-nopw",
        "-noxrecord",
        "-noxfixes",
        "-noxdamage",
    ])
    
    start_detached(vnc_args, vnc_env, "x11vnc.log")
    time.sleep(1)

    # 3b. Start a window manager so browser windows appear properly
    import shutil
    wm_candidates = [
        ("openbox", ["openbox", "--replace"]),
        ("fluxbox", ["fluxbox"]),
        ("xfwm4", ["xfwm4"]),
    ]
    wm_env = vnc_env.copy()
    wm_env["DISPLAY"] = display
    if auth:
        wm_env["XAUTHORITY"] = auth

    # Check if any WM is already running
    any_wm_running = False
    for wm_name, _ in wm_candidates:
        check = run(f"pgrep -x {wm_name}")
        if check.stdout.strip():
            print(f"{wm_name} already running (pid {check.stdout.strip()})")
            any_wm_running = True
            break

    if not any_wm_running:
        wm_started = False
        for wm_name, wm_cmd in wm_candidates:
            if shutil.which(wm_name):
                print(f"Starting {wm_name} window manager on {display}...")
                start_detached(wm_cmd, wm_env, f"/tmp/{wm_name}.log")
                time.sleep(1)
                wm_started = True
                break
        if not wm_started:
            print("WARNING: No window manager found (tried: openbox, fluxbox, xfwm4).")
            print("  Browser windows may not render properly. Install one with:")
            print("  apt-get install -y openbox")

    # 4. Start websockify
    # Use common paths for novnc
    novnc_paths = ["/usr/share/novnc/", "/usr/local/share/novnc/"]
    web_path = next((p for p in novnc_paths if os.path.exists(p)), "/usr/share/novnc/")
    
    # Use 6080 (standard for noVNC) or 8080. Using 6080 to avoid sudo requirements.
    port = 6080
    # Use 127.0.0.1 instead of localhost for stability
    print(f"Starting websockify on port {port} targeting 127.0.0.1:5900...")
    start_detached(
        ["websockify", "--web", web_path, str(port), "127.0.0.1:5900"],
        os.environ.copy(),
        "websockify.log",
    )
    
    time.sleep(2)
    
    # 5. Verify
    vnc_port = run("ss -tlnp 'sport = :5900'")
    web_port = run(f"ss -tlnp 'sport = :{port}'")
    print("\nStatus:")
    if ":5900" in vnc_port.stdout:
        print("[OK] x11vnc is listening on 5900")
    else:
        print("[FAIL] x11vnc is NOT listening (check x11vnc.log)")
        
    if f":{port}" in web_port.stdout:
        print(f"[OK] websockify is listening on {port}")
    else:
        print(f"[FAIL] websockify is NOT listening (check websockify.log)")

    print(f"\nIf both are OK, open: http://<vps-ip>/vnc.html")

if __name__ == "__main__":
    main()
