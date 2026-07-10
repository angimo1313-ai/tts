<#  Voice Studio 업데이트 — GitHub 비공개 저장소에서 최신 코드를 받아 적용.
    사용: .\update.ps1   (또는 앱 설정 탭의 '업데이트 확인' 버튼)  #>
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".git")) {
  Write-Host "git 저장소가 아닙니다. GitHub 연동(원격 등록) 후 사용하세요." -ForegroundColor Yellow
  exit 1
}

Write-Host "=== 현재 버전 ===" -ForegroundColor Cyan
git rev-parse --short HEAD

Write-Host "=== 업데이트 확인 (git pull) ===" -ForegroundColor Cyan
$before = git rev-parse HEAD
git pull --ff-only
$after = git rev-parse HEAD

if ($before -eq $after) {
  Write-Host "이미 최신 버전입니다." -ForegroundColor Green
  exit 0
}

Write-Host "새 버전 적용됨: $before -> $after" -ForegroundColor Green

# 의존성 변경 반영 (경량 앱 의존성)
Write-Host "=== 의존성 동기화 ===" -ForegroundColor Cyan
$env:UV_PYTHON_INSTALL_DIR = Join-Path $PSScriptRoot ".uvhome\python"
$env:UV_CACHE_DIR          = Join-Path $PSScriptRoot ".uvhome\cache"
if (Test-Path ".venv") {
  uv pip install --python .venv fastapi "uvicorn[standard]" python-multipart yt-dlp pydantic
} else {
  Write-Host ".venv 없음 — setup.ps1 을 먼저 실행하세요." -ForegroundColor Yellow
}

Write-Host "업데이트 완료. 앱을 재시작하면 적용됩니다." -ForegroundColor Cyan
