from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
import subprocess
import os
import psutil
from app.main_templates import templates

router = APIRouter(prefix="/syspanel", tags=["syspanel"])

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def get_syspanel(request: Request):
    # Basic system info
    cpu = psutil.cpu_percent(interval=0.1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    context = {
        "request": request,
        "cpu_percent": cpu,
        "mem_percent": memory.percent,
        "mem_used": round(memory.used / (1024**3), 2),
        "mem_total": round(memory.total / (1024**3), 2),
        "disk_percent": disk.percent,
        "disk_used": round(disk.used / (1024**3), 2),
        "disk_total": round(disk.total / (1024**3), 2)
    }
    return templates.TemplateResponse("pages/syspanel.html", context)

def run_command_in_background(cmd: str, cwd: str = None) -> str:
    try:
        # We need to run this command, but not block the UI completely. For simplicity, we capture output.
        # This will block the thread for git pull and cleanup, but it's fast. PM2 restart will also be fast.
        result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=120)
        output = result.stdout + "\n" + result.stderr if result.stderr else result.stdout
        return output or f"✅ Command executed successfully (no output)."
    except Exception as e:
        return f"❌ Error: {str(e)}"

@router.post("/cmd/git-pull", response_class=HTMLResponse)
def cmd_git_pull():
    output = run_command_in_background("git pull origin main", cwd=os.getcwd())
    return HTMLResponse(f"<pre class='text-sm text-green-400 font-mono whitespace-pre-wrap'>{output}</pre>")

@router.post("/cmd/pm2-restart", response_class=HTMLResponse)
def cmd_pm2_restart():
    # It takes a moment to restart
    output = run_command_in_background("pm2 restart all")
    return HTMLResponse(f"<pre class='text-sm text-green-400 font-mono whitespace-pre-wrap'>{output}\n\n🔄 PM2 components restarting...</pre>")

@router.post("/cmd/cleanup-db", response_class=HTMLResponse)
def cmd_cleanup_db():
    venv_cmd = "source venv/bin/activate && " if os.path.exists("venv") else ""
    output = run_command_in_background(f"{venv_cmd}python scripts/fix_garbage_pages.py", cwd=os.getcwd())
    return HTMLResponse(f"<pre class='text-sm text-green-400 font-mono whitespace-pre-wrap'>{output}</pre>")
