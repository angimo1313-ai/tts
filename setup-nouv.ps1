<#
  Voice Studio — uv 없이 설치 (python.org + venv + pip)

  일부 환경(클라우드 PC/VDI/마운트 디스크 등)은 uv 의 파이썬 관리 연산이
  "신뢰할 수 없는 탑재 지점"(os error 448)으로 막힌다. 이 스크립트는 표준
  python.org 파이썬과 venv/pip 만 사용해 그런 환경에서도 설치되게 한다.

  사용법:
    .\setup-nouv.ps1            # 기본(GPU) + F5-TTS
    .\setup-nouv.ps1 -Cpu       # CPU 용 PyTorch
    .\setup-nouv.ps1 -SoVITS    # GPT-SoVITS(한국어) 까지
  요구: Windows 10/11, 인터넷. 관리자 권한 불필요.
#>
param([switch]$Cpu, [switch]$SoVITS)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root
function Info($m) { Write-Host "`n=== $m ===" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "  $m" -ForegroundColor Green }

$PyVer = "3.10.11"
# 파이썬은 프로필 밖(공용)에 설치 — 프로필이 신뢰불가 마운트여도 안전
$PyDir = "C:\Users\Public\Python310"

# ---------- 1. python.org 3.10 ----------
Info "Python $PyVer 준비"
if (-not (Test-Path "$PyDir\python.exe")) {
  $ins = Join-Path $env:TEMP "py310_setup.exe"
  Ok "python.org 다운로드"
  Invoke-WebRequest "https://www.python.org/ftp/python/$PyVer/python-$PyVer-amd64.exe" -OutFile $ins
  Ok "무인 설치 → $PyDir"
  Start-Process $ins -ArgumentList "/quiet","InstallAllUsers=0","TargetDir=$PyDir",
    "Include_launcher=0","Include_test=0","Shortcuts=0","AssociateFiles=0" -Wait
  Remove-Item $ins -Force -ErrorAction SilentlyContinue
}
$SysPy = Join-Path $PyDir "python.exe"
if (-not (Test-Path $SysPy)) { throw "Python 설치 실패: $SysPy" }
Ok (& $SysPy --version)

# ---------- 2. .venv + 앱(경량) 의존성 ----------
Info "가상환경(.venv) 생성 + 앱 의존성"
if (-not (Test-Path ".venv\Scripts\python.exe")) { & $SysPy -m venv .venv }
$Py = Join-Path $Root ".venv\Scripts\python.exe"
& $Py -m pip install --upgrade pip
& $Py -m pip install fastapi "uvicorn[standard]" python-multipart yt-dlp pydantic pywebview
Ok "완료"

# ---------- 3. ffmpeg ----------
Info "ffmpeg 준비"
$ffmpegBin = Join-Path $Root "tools\ffmpeg\bin"
if (-not (Test-Path (Join-Path $ffmpegBin "ffmpeg.exe"))) {
  $tmp = Join-Path $env:TEMP "ffmpeg_vs.zip"
  Invoke-WebRequest "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip" -OutFile $tmp
  $ex = Join-Path $env:TEMP "ffmpeg_vs"; if (Test-Path $ex) { Remove-Item $ex -Recurse -Force }
  Expand-Archive $tmp $ex -Force
  $inner = Get-ChildItem $ex -Directory | Select-Object -First 1
  New-Item -ItemType Directory -Force (Join-Path $Root "tools\ffmpeg") | Out-Null
  Copy-Item (Join-Path $inner.FullName "bin") (Join-Path $Root "tools\ffmpeg\bin") -Recurse -Force
  Remove-Item $tmp -Force
  Ok "설치 완료"
} else { Ok "이미 설치됨" }

# ---------- 4. PyTorch ----------
Info "PyTorch 설치"
if ($Cpu) { & $Py -m pip install torch torchaudio }
else { & $Py -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118 }
Ok "완료"

# ---------- 5. 전처리 + F5-TTS ----------
Info "전처리 스택 + F5-TTS 설치"
& $Py -m pip install faster-whisper demucs soundfile librosa
& $Py -m pip install f5-tts
& $Py -m pip install "transformers==4.49.0" "datasets==3.6.0" "pyarrow==17.0.0"
& $Py -m pip uninstall -y torchcodec 2>$null
Ok "완료"

# ---------- 6. (옵션) GPT-SoVITS ----------
if ($SoVITS) {
  Info "GPT-SoVITS 준비"
  New-Item -ItemType Directory -Force (Join-Path $Root "engines") | Out-Null
  $sov = Join-Path $Root "engines\GPT-SoVITS"
  if (-not (Test-Path $sov)) {
    Ok "GPT-SoVITS 다운로드"
    $zip = Join-Path $env:TEMP "gptsovits.zip"
    Invoke-WebRequest "https://codeload.github.com/RVC-Boss/GPT-SoVITS/zip/refs/heads/main" -OutFile $zip
    $ex = Join-Path $env:TEMP "gptsovits_ex"; if (Test-Path $ex) { Remove-Item $ex -Recurse -Force }
    Expand-Archive $zip $ex -Force
    Move-Item (Get-ChildItem $ex -Directory | Select-Object -First 1).FullName $sov
    Remove-Item $zip -Force
  }

  Info "GPT-SoVITS 가상환경(.venv-sovits)"
  if (-not (Test-Path ".venv-sovits\Scripts\python.exe")) { & $SysPy -m venv .venv-sovits }
  $PyS = Join-Path $Root ".venv-sovits\Scripts\python.exe"
  & $PyS -m pip install --upgrade pip
  if ($Cpu) { & $PyS -m pip install torch torchaudio }
  else { & $PyS -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118 }
  & $PyS -m pip install -r (Join-Path $Root "engines\requirements-sovits-win.txt")

  # 영어 처리용 NLTK 데이터(없으면 생성 실패) + 언어감지 캐시 폴더
  & $PyS -c "import nltk; [nltk.download(x) for x in ['averaged_perceptron_tagger_eng','averaged_perceptron_tagger','cmudict']]"
  New-Item -ItemType Directory -Force (Join-Path $sov "GPT_SoVITS\pretrained_models\fast_langdetect") | Out-Null

  # 컴파일 회피 shim (jieba_fast, eunjeon) + korean.py 패치
  $sp = Join-Path $Root ".venv-sovits\Lib\site-packages"
  New-Item -ItemType Directory -Force (Join-Path $sp "jieba_fast") | Out-Null
  Copy-Item (Join-Path $Root "engines\jieba_fast_shim.py") (Join-Path $sp "jieba_fast\__init__.py") -Force
  New-Item -ItemType Directory -Force (Join-Path $sp "eunjeon") | Out-Null
  Copy-Item (Join-Path $Root "engines\eunjeon_shim.py") (Join-Path $sp "eunjeon\__init__.py") -Force
  & $PyS (Join-Path $Root "scripts\patch_sovits_korean.py")

  Info "GPT-SoVITS v2 모델 다운로드"
  & $PyS (Join-Path $Root "scripts\download_sovits_models.py")
  Ok "GPT-SoVITS 준비 완료"
}

Info "세팅 완료"
Ok "실행:  .\run.ps1   (또는 바탕화면 아이콘)"
