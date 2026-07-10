# Voice Studio 자체 업데이트 — 최신 코드 적용 + pywebview 보장 + 자동 재실행
# 실행: irm https://raw.githubusercontent.com/angimo1313-ai/tts/main/scripts/self_update.ps1 | iex
$ErrorActionPreference = "Stop"

# 앱 폴더 자동 탐지 — 현재 폴더 우선, 그다음 흔한 설치 경로들.
# (irm|iex 로 실행 시엔 먼저 'cd 앱폴더' 하면 현재 폴더로 잡힘)
$cands = @(
  (Get-Location).Path,
  "C:\VoiceStudio",
  "$env:LOCALAPPDATA\Programs\Voice Studio",
  "C:\Users\Public\VoiceStudio",
  "$([Environment]::GetFolderPath('Desktop'))\Voice Studio"
)
$app = $cands | Where-Object { $_ -and (Test-Path (Join-Path $_ "launcher.pyw")) } | Select-Object -First 1
if (-not $app) {
  Write-Host "Voice Studio 설치 폴더를 찾지 못했습니다." -ForegroundColor Red
  Write-Host "앱 폴더로 이동한 뒤 다시 실행하세요:  cd '앱폴더경로'  그리고 원라이너 재실행" -ForegroundColor Yellow
  return
}
Write-Host "업데이트 대상: $app" -ForegroundColor Cyan

# 실행 중인 앱 종료 (파일 잠금 해제) — 이 앱 폴더의 python/pythonw 만 정확히
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
  Where-Object { $_.CommandLine -and $_.CommandLine.ToLower().Contains($app.ToLower()) } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1

# 최신 코드 다운로드(공개 저장소)
$zip = Join-Path $env:TEMP "vs_update.zip"
Write-Host "최신 코드 다운로드 중..."
Invoke-WebRequest "https://codeload.github.com/angimo1313-ai/tts/zip/refs/heads/main" -OutFile $zip
$ex = Join-Path $env:TEMP "vs_update_ex"; if (Test-Path $ex) { Remove-Item $ex -Recurse -Force }
Expand-Archive $zip $ex -Force
$src = (Get-ChildItem $ex -Directory | Select-Object -First 1).FullName

# 코드만 덮기 (사용자 설정/토큰/환경/모델 보존)
robocopy $src $app /E /XF config.json github_token.txt /XD .git /NFL /NDL /NJH /NJS | Out-Null
Remove-Item $zip -Force -ErrorAction SilentlyContinue
Remove-Item $ex -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "코드 업데이트 완료" -ForegroundColor Green

# 네이티브 창(pywebview) 보장
$py = Join-Path $app ".venv\Scripts\python.exe"
if (Test-Path $py) { & $py -m pip install --quiet --disable-pip-version-check pywebview 2>$null }

# 바로가기를 네이티브 앱으로 갱신
$mk = Join-Path $app "scripts\make_shortcut.ps1"
if (Test-Path $mk) { try { & powershell -NoProfile -ExecutionPolicy Bypass -File $mk } catch {} }

# 자동 재실행
$pyw = Join-Path $app ".venv\Scripts\pythonw.exe"
if (Test-Path $pyw) {
  Start-Process $pyw -ArgumentList "launcher.pyw" -WorkingDirectory $app
  Write-Host "업데이트 완료 — 앱을 다시 실행했습니다!" -ForegroundColor Green
} else {
  Write-Host "업데이트 완료 — 앱을 다시 켜세요." -ForegroundColor Green
}
