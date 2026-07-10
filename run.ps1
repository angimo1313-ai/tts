<#  Voice Studio 실행 — 브라우저에서 GUI 를 엽니다.  #>
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv")) {
  Write-Host "환경이 없습니다. 먼저 .\setup.ps1 을 실행하세요." -ForegroundColor Yellow
  exit 1
}

$env:PYTHONUTF8 = "1"  # 한국어 로그 깨짐 방지
$url = "http://127.0.0.1:7860"
Write-Host "Voice Studio 실행 중 → $url" -ForegroundColor Cyan
Start-Process $url
uv run uvicorn app.server:app --host 127.0.0.1 --port 7860
