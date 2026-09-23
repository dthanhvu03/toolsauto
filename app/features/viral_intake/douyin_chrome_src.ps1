param(
  [Parameter(Mandatory = $true)][string]$VideoUrl,
  [int]$Port = 19222,
  [int]$WaitSec = 22
)

$ErrorActionPreference = "Stop"
$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
if (-not (Test-Path $chrome)) {
  $chrome = "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe"
}
if (-not (Test-Path $chrome)) {
  @{ ok = $false; error = "chrome_not_found" } | ConvertTo-Json -Compress
  exit 1
}

$profile = Join-Path $env:TEMP "toolsauto-dy-chrome"
New-Item -ItemType Directory -Force -Path $profile | Out-Null

$chromeArgs = @(
  "--remote-debugging-port=$Port",
  "--user-data-dir=$profile",
  "--no-first-run",
  "--no-default-browser-check",
  "--disable-background-networking",
  "--remote-allow-origins=*",
  "--autoplay-policy=no-user-gesture-required",
  "--window-size=900,700",
  $VideoUrl
)

$proc = Start-Process -FilePath $chrome -WorkingDirectory "C:\Windows\Temp" -PassThru -ArgumentList $chromeArgs
try {
  $ready = $false
  for ($i = 0; $i -lt 24; $i++) {
    try {
      $null = Invoke-RestMethod "http://127.0.0.1:$Port/json/version"
      $ready = $true
      break
    } catch { Start-Sleep -Milliseconds 250 }
  }
  if (-not $ready) { throw "CDP not ready on $Port" }

  Start-Sleep -Seconds 2
  $tabs = Invoke-RestMethod "http://127.0.0.1:$Port/json"
  $page = $tabs | Where-Object { $_.type -eq "page" -and $_.webSocketDebuggerUrl } | Select-Object -First 1
  if (-not $page) { throw "no_cdp_page" }

  $ws = New-Object System.Net.WebSockets.ClientWebSocket
  $ct = [System.Threading.CancellationToken]::None
  $ws.ConnectAsync([Uri]$page.webSocketDebuggerUrl, $ct).Wait()

  function Send-Cdp([int]$id, [string]$method, $params) {
    $obj = @{ id = $id; method = $method }
    if ($null -ne $params) { $obj["params"] = $params }
    $json = ($obj | ConvertTo-Json -Depth 12 -Compress)
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    $seg = [System.ArraySegment[byte]]::new($bytes)
    $ws.SendAsync($seg, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $ct).Wait()
  }
  function Recv-Cdp {
    $buf = New-Object byte[] 262144
    $sb = New-Object System.Text.StringBuilder
    do {
      $seg = [System.ArraySegment[byte]]::new($buf)
      $r = $ws.ReceiveAsync($seg, $ct).Result
      [void]$sb.Append([System.Text.Encoding]::UTF8.GetString($buf, 0, $r.Count))
    } while (-not $r.EndOfMessage)
    return $sb.ToString()
  }

  Send-Cdp 1 "Page.enable" @{}
  Send-Cdp 2 "Page.navigate" @{ url = $VideoUrl }
  $deadline = [DateTime]::UtcNow.AddSeconds($WaitSec)
  $found = $null
  $expr = @'
(() => {
  const ok = (s) => s && /^https?:/i.test(s) && !s.includes("uuu_") && !s.includes("douyinstatic.com/obj/douyin-pc-web/") && (s.includes("mime_type=video") || s.includes("zjcdn.com") || s.includes("douyinvod") || s.includes("bytevod") || s.includes("tos-cn-ve") || s.includes("/aweme/v1/play"));
  const vids = [...document.querySelectorAll("video")];
  const hit = vids.map(v => v.currentSrc || v.src).find(ok);
  return JSON.stringify({ href: location.href, title: document.title, src: hit || "", n: vids.length });
})()
'@
  $id = 10
  while ([DateTime]::UtcNow -lt $deadline) {
    Send-Cdp $id "Runtime.evaluate" @{ expression = $expr; returnByValue = $true }
    for ($k = 0; $k -lt 12; $k++) {
      $raw = Recv-Cdp
      if ($raw -match ("""id"":$id")) {
        try {
          $msg = $raw | ConvertFrom-Json
          $val = $msg.result.result.value
          if ($val -is [string]) { $parsed = $val | ConvertFrom-Json } else { $parsed = $val }
          if ($parsed.src -and $parsed.src.StartsWith("http")) {
            $found = $parsed
            break
          }
        } catch {}
        break
      }
    }
    if ($found) { break }
    $id++
    Start-Sleep -Milliseconds 800
  }
  try { $ws.Dispose() } catch {}
  if ($found) {
    @{ ok = $true; src = $found.src; title = $found.title; href = $found.href } | ConvertTo-Json -Compress
  } else {
    @{ ok = $false; error = "no_http_video_src" } | ConvertTo-Json -Compress
  }
} catch {
  @{ ok = $false; error = $_.Exception.Message } | ConvertTo-Json -Compress
} finally {
  try { & taskkill.exe /F /T /PID $proc.Id | Out-Null } catch {}
}
