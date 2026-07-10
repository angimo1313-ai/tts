<#  Voice Studio 바로가기 생성 — 바탕화면 + 시작 메뉴.
    pythonw.exe 로 launcher.pyw 를 실행(콘솔 없음), 아이콘 적용.  #>
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent

$pythonw = Join-Path $Root ".venv\Scripts\pythonw.exe"
$launcher = Join-Path $Root "launcher.pyw"
$icon = Join-Path $Root "app\static\icon.ico"

if (-not (Test-Path $pythonw)) { Write-Host "먼저 setup.ps1 을 실행하세요 (.venv 없음)" -ForegroundColor Yellow; exit 1 }

function New-Shortcut($path) {
  $ws = New-Object -ComObject WScript.Shell
  $sc = $ws.CreateShortcut($path)
  $sc.TargetPath = $pythonw
  $sc.Arguments = "`"$launcher`""
  $sc.WorkingDirectory = $Root
  $sc.IconLocation = $icon
  $sc.Description = "Voice Studio - 한국어 음성 복제 TTS"
  $sc.WindowStyle = 7   # 최소화(콘솔 안뜸)
  $sc.Save()
  Write-Host "  바로가기 생성: $path" -ForegroundColor Green
}

# 바탕화면
$desktop = [Environment]::GetFolderPath("Desktop")
New-Shortcut (Join-Path $desktop "Voice Studio.lnk")

# 시작 메뉴
$startMenu = Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs"
New-Shortcut (Join-Path $startMenu "Voice Studio.lnk")

Write-Host "완료 — 이제 바탕화면의 Voice Studio 아이콘을 더블클릭하면 앱이 열립니다." -ForegroundColor Cyan
