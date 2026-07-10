<#  Voice Studio 실행 — 브라우저에서 GUI 를 엽니다.  #>
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv")) {
  Write-Host "환경이 없습니다. 먼저 .\setup.ps1 을 실행하세요." -ForegroundColor Yellow
  exit 1
}

$env:PYTHONUTF8 = "1"  # 한국어 로그 깨짐 방지
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Host "환경이 없습니다. 먼저 .\setup.ps1 을 실행하세요." -ForegroundColor Yellow; exit 1 }
$url = "http://127.0.0.1:7860"
Write-Host "Voice Studio 실행 중 → $url" -ForegroundColor Cyan
Start-Process $url
# uv 대신 .venv 파이썬 직접 실행 (일부 PC 의 Roaming 마운트 문제 회피)
& $py -m uvicorn app.server:app --host 127.0.0.1 --port 7860
