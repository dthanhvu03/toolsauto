$ErrorActionPreference = 'Stop'
$env:SHOPEE_PROFILE_DIR = 'C:\Users\Admin\.shopee-mcp\chrome-profile'
$env:SHOPEE_DOMAIN = 'shopee.vn'
$env:SHOPEE_BRIDGE_LISTEN_HOST = '192.168.112.1'
$env:SHOPEE_BRIDGE_ALLOWED_PEERS = '192.168.112.133,192.168.112.1'
$env:SHOPEE_BRIDGE_PORT = '9224'
$repo = '\\wsl.localhost\Ubuntu\home\vu\toolsauto'
try {
    & wsl.exe -d Ubuntu --cd /home/vu/toolsauto bash -lc 'pm2 stop shopee-mcp >/dev/null'
    if ($LASTEXITCODE -ne 0) { throw 'bridge_stop_failed' }
    $profile = [IO.Path]::GetFullPath($env:SHOPEE_PROFILE_DIR)
    $stale = @(Get-CimInstance Win32_Process -Filter "Name = 'chrome.exe' OR Name = 'chromium.exe'" | Where-Object { $_.CommandLine -and $_.CommandLine.IndexOf($profile, [StringComparison]::OrdinalIgnoreCase) -ge 0 })
    foreach ($process in $stale) { Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue }
    $locks = @()
    foreach ($name in @('lockfile','SingletonLock','SingletonSocket','SingletonCookie')) {
        $target = [IO.Path]::GetFullPath((Join-Path $profile $name))
        if ([IO.Path]::GetDirectoryName($target) -ne $profile) { throw 'lock_path_outside_profile' }
        $before = Test-Path -LiteralPath $target
        if ($before) { Remove-Item -LiteralPath $target -Force }
        $after = Test-Path -LiteralPath $target
        $locks += @{ name=$name; existed_before=$before; exists_after=$after }
        if ($after) { throw 'profile_lock_cleanup_failed' }
    }
    $cleanup = @{ at=[DateTime]::UtcNow.ToString('o'); profile_processes_stopped=$stale.Count; locks=$locks }
    [IO.File]::WriteAllText((Join-Path $repo 'reports\plan177\lifecycle-b-profile-cleanup-20261119.json'), ($cleanup | ConvertTo-Json -Depth 5), (New-Object Text.UTF8Encoding($false)))
    & 'C:\Program Files\nvm\nodejs\node.exe' (Join-Path $repo 'reports\plan177\lifecycle-b-native-smoke-20261119.mjs')
    Write-Output ('repo_smoke_process_exit=' + $LASTEXITCODE)
} finally {
    & wsl.exe -d Ubuntu --cd /home/vu/toolsauto bash -lc 'pm2 start shopee-mcp >/dev/null'
    Write-Output ('legacy_restore_exit=' + $LASTEXITCODE)
}
