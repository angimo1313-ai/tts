<#  Voice Studio 실행 — 콘솔 없이 앱 창을 띄웁니다.  #>
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$pyw = Join-Path $PSScriptRoot ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pyw)) {
  Write-Host "환경이 없습니다. 먼저 환경 설치를 실행하세요." -ForegroundColor Yellow
  exit 1
}

# pythonw 런처 → 서버(창 없음) + Chrome 앱 창. run.ps1 은 바로 종료(콘솔 안 남음).
Start-Process $pyw -ArgumentList "launcher.pyw" -WorkingDirectory $PSScriptRoot
Write-Host "Voice Studio 를 실행했습니다 — 앱 창이 곧 뜹니다." -ForegroundColor Cyan
