# ToolsAuto local start (Windows)
# Usage: .\start.ps1 [-Port 8001] [-SkipMigrate]
param(
    [int]$Port = 0,
    [switch]$SkipMigrate
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if ($Port -le 0) {
    if ($env:WEB_PORT) {
        $Port = [int]$env:WEB_PORT
    } else {
        # Load default from app.config if PYTHONPATH works; else 8002
        $Port = 8002
        if (Test-Path "venv\Scripts\python.exe") {
            $env:PYTHONPATH = $PSScriptRoot
            $p = & .\venv\Scripts\python.exe -c 'import app.config as c; print(c.WEB_PORT)' 2>$null
            if ($p) { $Port = [int]$p }
        }
    }
}

if (-not (Test-Path ".env")) {
    Write-Error "Missing .env - copy from .env.example and fill ADMIN_*, SECRET_KEY, DATABASE_URL"
}

if (-not (Test-Path "venv\Scripts\python.exe")) {
    Write-Error "Missing venv. Run: py -3 -m venv venv; .\venv\Scripts\pip install -r requirements.txt"
}

$env:PYTHONPATH = $PSScriptRoot
$py = Join-Path $PSScriptRoot "venv\Scripts\python.exe"

Write-Host "=== ToolsAuto - local start (port $Port) ===" -ForegroundColor Cyan

if (-not $SkipMigrate) {
    Write-Host "DB schema upgrade..." -ForegroundColor Yellow
    & $py manage.py db upgrade
}

Write-Host "Web: http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host "Login: values from .env (ADMIN_USERNAME / ADMIN_PASSWORD)" -ForegroundColor Green
& $py manage.py serve --host 127.0.0.1 --port $Port --reload
