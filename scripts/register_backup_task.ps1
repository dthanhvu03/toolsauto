<#
Dang ky lich backup Postgres bang Windows Task Scheduler.

Vi sao khong dung PM2: PM2 chi co tren VPS. May local chay bang
`start.ps1 -Stack` -> local_supervisor.py, khong he co PM2, nen app "DB_Backup"
trong ecosystem.config.js KHONG BAO GIO chay o local.

Vi sao khong gan vao local_supervisor: backup can chay ca khi Owner khong bat
stack. Task Scheduler doc lap voi ung dung nen dung hon.

    .\scripts\register_backup_task.ps1              # dang ky / cap nhat
    .\scripts\register_backup_task.ps1 -RunNow      # dang ky roi chay thu luon
    .\scripts\register_backup_task.ps1 -Remove      # go bo
#>
param(
    [string]$Time = "03:00",
    [int]$Keep = 14,
    [switch]$RunNow,
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$TaskName = "ToolsAuto-DB-Backup"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot "venv\Scripts\python.exe"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Da go task '$TaskName'." -ForegroundColor Yellow
    return
}

if (-not (Test-Path $Python)) { throw "Khong thay interpreter: $Python" }

$action = New-ScheduledTaskAction -Execute $Python `
    -Argument "manage.py db backup --keep $Keep" -WorkingDirectory $ProjectRoot

$trigger = New-ScheduledTaskTrigger -Daily -At $Time

# StartWhenAvailable: may ca nhan hay tat ban dem - lo gio thi chay bu khi bat may,
# thay vi bo qua ca ngay hom do.
# DontStopIfGoingOnBatteries: laptop rut sac van backup.
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "Backup Postgres cua ToolsAuto (pg_dump, giu $Keep ban)" `
    -Force | Out-Null

Write-Host "Da dang ky '$TaskName' - chay hang ngay luc $Time, giu $Keep ban dump." -ForegroundColor Green

if ($RunNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Da kich hoat chay thu. Xem ket qua: Get-ScheduledTaskInfo $TaskName" -ForegroundColor Cyan
}
