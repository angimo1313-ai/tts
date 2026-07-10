# Voice Studio self-restart helper (ASCII only - no BOM needed for PS 5.1).
# Launched detached by app/server.py _schedule_restart().
# Closes the running app (launcher + server + its webview) and relaunches it.
# Logs every step to data\restart.log so failures are diagnosable.
param(
  [Parameter(Mandatory = $true)][string]$Root,
  [switch]$DryRun
)

$ErrorActionPreference = "Continue"
$logDir = Join-Path $Root "data"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force $logDir | Out-Null }
$log = Join-Path $logDir "restart.log"

function Log([string]$m) {
  $line = "{0} {1}" -f (Get-Date).ToString("yyyy-MM-dd HH:mm:ss"), $m
  Add-Content -Path $log -Value $line -Encoding UTF8
}

Log "===== restart begin (Root=$Root DryRun=$DryRun) ====="

# Give the HTTP response time to flush before we start killing things.
Start-Sleep -Seconds 2

# 1) Kill python/pythonw processes that belong to THIS app folder only.
#    Both the launcher and the uvicorn server run from $Root\.venv\Scripts\pythonw.exe,
#    so their command line contains $Root -> precise match, no collateral kills.
try {
  $py = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
        Where-Object { $_.CommandLine -and $_.CommandLine.ToLower().Contains($Root.ToLower()) }
  foreach ($p in $py) {
    Log ("kill python pid={0} cmd={1}" -f $p.ProcessId, $p.CommandLine)
    if (-not $DryRun) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
  }
  if (-not $py) { Log "no app python process found" }
} catch { Log "python-kill error: $_" }

# 2) Kill any browser/webview process using this app's profile (Chrome app-mode fallback).
$prof = Join-Path $Root ".appprofile"
try {
  $win = Get-CimInstance Win32_Process |
         Where-Object { $_.CommandLine -and $_.CommandLine.Contains($prof) }
  foreach ($w in $win) {
    Log ("kill window pid={0}" -f $w.ProcessId)
    if (-not $DryRun) { Stop-Process -Id $w.ProcessId -Force -ErrorAction SilentlyContinue }
  }
} catch { Log "window-kill error: $_" }

# 3) Wait until port 7860 is actually released (max 12s) so the new server can bind.
for ($i = 0; $i -lt 24; $i++) {
  $busy = Get-NetTCPConnection -LocalPort 7860 -State Listen -ErrorAction SilentlyContinue
  if (-not $busy) { break }
  Start-Sleep -Milliseconds 500
}
Log "port 7860 free-check done (waited $($i*0.5)s)"

# 4) Relaunch the app.
$pyw = Join-Path $Root ".venv\Scripts\pythonw.exe"
$launcher = Join-Path $Root "launcher.pyw"
if (-not (Test-Path $pyw)) { Log "ERROR pythonw missing: $pyw"; exit 1 }
if (-not (Test-Path $launcher)) { Log "ERROR launcher missing: $launcher"; exit 1 }
if ($DryRun) { Log "DryRun -> skip relaunch"; Log "===== restart end ====="; exit 0 }

try {
  Start-Process -FilePath $pyw -ArgumentList "`"$launcher`"" -WorkingDirectory $Root
  Log "relaunched: $pyw $launcher"
} catch {
  Log "relaunch error: $_"
  exit 1
}
Log "===== restart end ====="
