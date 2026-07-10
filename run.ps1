<#  Voice Studio 실행 — 콘솔 없이 앱 창을 띄웁니다.  #>
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$pyw = Join-Path $PSScriptRoot ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pyw)) {
  Write-Host "환경이 없습니다. 먼저 환경 설치를 실행하세요." -ForegroundColor Yellow
  exit 1
}

# 네이티브 GUI(PySide6) 실행 — 콘솔·웹뷰 없이 진짜 프로그램 창.
Start-Process $pyw -ArgumentList "app_native.py" -WorkingDirectory $PSScriptRoot
Write-Host "Voice Studio 를 실행했습니다 — 프로그램 창이 곧 뜹니다." -ForegroundColor Cyan
