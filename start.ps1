# ToolsAuto local start (Windows)
# Usage: .\start.ps1 [-Port 8001] [-SkipMigrate]
param(
    [int]$Port = 8001,
    [switch]$SkipMigrate
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".env")) {
    Write-Error "Missing .env — copy from .env.example and fill ADMIN_*, SECRET_KEY, DATABASE_URL"
}

if (-not (Test-Path "venv\Scripts\python.exe")) {
    Write-Error "Missing venv. Run: py -3 -m venv venv; .\venv\Scripts\pip install -r requirements.txt"
}

$env:PYTHONPATH = $PSScriptRoot
$py = Join-Path $PSScriptRoot "venv\Scripts\python.exe"

Write-Host "=== ToolsAuto — local start (port $Port) ===" -ForegroundColor Cyan

if (-not $SkipMigrate) {
    Write-Host "DB schema upgrade..." -ForegroundColor Yellow
    & $py manage.py db upgrade
}

Write-Host "Web: http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host "Login: values from .env (ADMIN_USERNAME / ADMIN_PASSWORD)" -ForegroundColor Green
& $py manage.py serve --host 127.0.0.1 --port $Port --reload
