# ToolsAuto local start (Windows)
# Usage:
#   .\start.ps1                  # web only (legacy)
#   .\start.ps1 -Stack           # web + maintenance + FB publisher (PLAN-048)
#   .\start.ps1 -Port 8001 -Stack
param(
    [int]$Port = 0,
    [switch]$SkipMigrate,
    [switch]$Stack,
    [switch]$Lan   # ADR-044: nghe trên mang nha (0.0.0.0) de dien thoai mo duoc link "Mo tren dien thoai"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Refresh PATH from Machine+User so winget tools (ffmpeg) work without closing Cursor
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
            [System.Environment]::GetEnvironmentVariable("Path", "User")

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

$BindHost = "127.0.0.1"
if ($Lan) {
    $BindHost = "0.0.0.0"
    $lanIp = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } | Select-Object -First 1).IPAddress
    Write-Host "Web (LAN): http://${lanIp}:$Port  <- dat vao Thiet lap 'Dia chi mo tool tu dien thoai'" -ForegroundColor Green
}
Write-Host "Web: http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host "Login: values from .env (ADMIN_USERNAME / ADMIN_PASSWORD)" -ForegroundColor Green

if ($Stack) {
    Write-Host "Mode: STACK (web + maintenance + FB publisher + AI generator)" -ForegroundColor Green
    & $py manage.py stack --host $BindHost --port $Port --no-reload-web
} else {
    Write-Host "Mode: WEB only (use -Stack for supervised workers)" -ForegroundColor Yellow
    & $py manage.py serve --host $BindHost --port $Port --reload
}
