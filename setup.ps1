<#
  Voice Studio — 초기 세팅 스크립트 (새 컴퓨터에서 원클릭 부팅)

  사용법:
    .\setup.ps1              # 기본: 앱 + ffmpeg + PyTorch(GPU) + 전처리 + F5-TTS
    .\setup.ps1 -Light       # GUI만 빠르게 (ML 제외)
    .\setup.ps1 -Cpu         # GPU 없이 CPU용 PyTorch
    .\setup.ps1 -SoVITS      # GPT-SoVITS 까지 설치

  요구: Windows 10/11. 관리자 권한 불필요.
#>
param(
  [switch]$Light,
  [switch]$Cpu,
  [switch]$SoVITS
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root
function Info($m) { Write-Host "`n=== $m ===" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "  $m" -ForegroundColor Green }

# ---------- 0. uv 데이터 위치를 앱 폴더 안으로 (중요) ----------
# 일부 PC 는 AppData\Roaming 이 OneDrive/로밍프로필로 "신뢰할 수 없는 탑재 지점"이 되어
# uv 기본 파이썬 위치(Roaming\uv\python)를 읽지 못한다(os error 448). 앱 폴더(로컬)로 돌린다.
$env:UV_PYTHON_INSTALL_DIR = Join-Path $Root ".uvhome\python"
$env:UV_CACHE_DIR          = Join-Path $Root ".uvhome\cache"
New-Item -ItemType Directory -Force $env:UV_PYTHON_INSTALL_DIR | Out-Null
New-Item -ItemType Directory -Force $env:UV_CACHE_DIR | Out-Null

# ---------- 1. uv 확인/설치 ----------
Info "uv 확인"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Ok "uv 미설치 — 설치 중"
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  $env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"
}
Ok (uv --version)

# ---------- 2. Python 3.10 ----------
Info "Python 3.10 준비"
# 프로필의 깨진 uv python shim 제거 — 신뢰불가 마운트(Roaming)를 가리켜 uv 를 혼란시킨다.
Get-ChildItem "$env:USERPROFILE\.local\bin\python*.exe" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
uv python install 3.10
# 관리형 파이썬의 실제 exe 경로를 직접 사용 (PATH 상의 shim 회피)
$py310 = (Get-ChildItem (Join-Path $env:UV_PYTHON_INSTALL_DIR "cpython-3.10*\python.exe") -ErrorAction SilentlyContinue | Select-Object -First 1).FullName
if (-not $py310) { throw "Python 3.10 을 찾지 못했습니다 ($env:UV_PYTHON_INSTALL_DIR). 앱이 신뢰되는 위치(예: C:\Users\Public\VoiceStudio)에 있는지 확인하세요." }
Ok "Python: $py310"

# ---------- 3. venv 생성 + 앱(경량) 의존성 ----------
Info "가상환경(.venv) 생성 + 앱 의존성 설치 (FastAPI, yt-dlp 등)"
uv venv --python $py310 .venv
uv pip install --python .venv fastapi "uvicorn[standard]" python-multipart yt-dlp pydantic
Ok "완료"

if ($Light) { Ok "Light 모드 — 여기까지. run.ps1 로 GUI 실행 가능"; exit 0 }

# ---------- 4. ffmpeg (정적 빌드) ----------
Info "ffmpeg 준비"
$ffmpegBin = Join-Path $Root "tools\ffmpeg\bin"
if (-not (Test-Path (Join-Path $ffmpegBin "ffmpeg.exe"))) {
  $tmp = Join-Path $env:TEMP "ffmpeg_vs.zip"
  $url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
  Ok "다운로드 중… ($url)"
  Invoke-WebRequest -Uri $url -OutFile $tmp
  $extract = Join-Path $env:TEMP "ffmpeg_vs"
  if (Test-Path $extract) { Remove-Item $extract -Recurse -Force }
  Expand-Archive $tmp -DestinationPath $extract -Force
  $inner = Get-ChildItem $extract -Directory | Select-Object -First 1
  New-Item -ItemType Directory -Force (Join-Path $Root "tools\ffmpeg") | Out-Null
  Copy-Item (Join-Path $inner.FullName "bin") (Join-Path $Root "tools\ffmpeg\bin") -Recurse -Force
  Remove-Item $tmp -Force
  Ok "설치 완료 → tools\ffmpeg\bin"
} else { Ok "이미 설치됨" }

# ---------- 5. PyTorch ----------
Info "PyTorch 설치"
if ($Cpu) {
  uv pip install --python .venv torch torchaudio
} else {
  # CUDA 11.8 (GTX 10xx / RTX 20xx 호환)
  uv pip install --python .venv torch torchaudio --index-url https://download.pytorch.org/whl/cu118
}
Ok "완료"

# ---------- 6. 전처리 스택 ----------
Info "전처리 스택 설치 (faster-whisper, demucs, soundfile)"
uv pip install --python .venv faster-whisper demucs soundfile librosa
Ok "완료"

# ---------- 7. F5-TTS ----------
Info "F5-TTS 설치"
uv pip install --python .venv f5-tts
# 초신형 transformers/datasets 5.x + pyarrow 24 는 Windows 에서 네이티브 충돌을 일으킴.
# F5-TTS 가 검증된 안정 조합으로 핀 고정하고, 깨진 torchcodec(선택 의존성) 제거.
Ok "안정 버전 핀 고정 (transformers/datasets/pyarrow)"
uv pip install --python .venv "transformers==4.49.0" "datasets==3.6.0" "pyarrow==17.0.0"
uv pip uninstall --python .venv torchcodec 2>$null
Ok "완료"

# ---------- 8. (옵션) GPT-SoVITS (한국어 주력 엔진) ----------
if ($SoVITS) {
  Info "GPT-SoVITS 준비 (별도 격리 환경)"
  New-Item -ItemType Directory -Force (Join-Path $Root "engines") | Out-Null
  $sov = Join-Path $Root "engines\GPT-SoVITS"
  if (-not (Test-Path $sov)) {
    if (Get-Command git -ErrorAction SilentlyContinue) {
      git clone --depth 1 https://github.com/RVC-Boss/GPT-SoVITS.git $sov
    } else {
      # git 이 없는 PC 대비 — zip 으로 내려받아 배치
      Ok "git 없음 — GPT-SoVITS zip 다운로드"
      $zip = Join-Path $env:TEMP "gptsovits.zip"
      Invoke-WebRequest "https://codeload.github.com/RVC-Boss/GPT-SoVITS/zip/refs/heads/main" -OutFile $zip
      $ex = Join-Path $env:TEMP "gptsovits_ex"
      if (Test-Path $ex) { Remove-Item $ex -Recurse -Force }
      Expand-Archive $zip $ex -Force
      $inner = Get-ChildItem $ex -Directory | Select-Object -First 1
      Move-Item $inner.FullName $sov
      Remove-Item $zip -Force
    }
  }
  Ok "레포 준비 완료"

  # 별도 venv + torch(cu118 또는 cpu)
  if (-not (Test-Path (Join-Path $Root ".venv-sovits"))) { uv venv --python 3.10 .venv-sovits }
  if ($Cpu) { uv pip install --python .venv-sovits torch torchaudio }
  else { uv pip install --python .venv-sovits torch torchaudio --index-url https://download.pytorch.org/whl/cu118 }

  # 축소 의존성(Windows 휠 전용: 컴파일 필요/비한국어 패키지 제외)
  uv pip install --python .venv-sovits -r (Join-Path $Root "engines\requirements-sovits-win.txt")

  # jieba_fast(중국어,컴파일 불가) → 순수 파이썬 jieba 로 대체하는 shim
  $shimDir = Join-Path $Root ".venv-sovits\Lib\site-packages\jieba_fast"
  New-Item -ItemType Directory -Force $shimDir | Out-Null
  Copy-Item (Join-Path $Root "engines\jieba_fast_shim.py") (Join-Path $shimDir "__init__.py") -Force

  # eunjeon(mecab-ko, 컴파일 불가) → kiwipiepy 기반 shim 으로 대체 (한국어 G2P)
  $eunjeonDir = Join-Path $Root ".venv-sovits\Lib\site-packages\eunjeon"
  New-Item -ItemType Directory -Force $eunjeonDir | Out-Null
  Copy-Item (Join-Path $Root "engines\eunjeon_shim.py") (Join-Path $eunjeonDir "__init__.py") -Force

  # korean.py 패치: win_G2p 대신 표준 g2pk2 + eunjeon shim 사용
  & (Join-Path $Root ".venv-sovits\Scripts\python.exe") (Join-Path $Root "scripts\patch_sovits_korean.py")

  # 사전학습 v2 모델 다운로드(검증 포함)
  Info "GPT-SoVITS v2 모델 다운로드"
  & (Join-Path $Root ".venv-sovits\Scripts\python.exe") (Join-Path $Root "scripts\download_sovits_models.py")
  Ok "GPT-SoVITS 준비 완료 (한국어 = 설정 탭에서 GPT-SoVITS 선택)"
}

Info "세팅 완료"
Ok "GUI 실행:  .\run.ps1"
