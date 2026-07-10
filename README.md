# Voice Studio 🎙️

유튜브 영상의 음성으로 **나만의 한국어 목소리**를 학습하고, 장문을 자연스럽게 읽어주는 로컬 TTS 앱.
애플 감성의 심플한 GUI(다크/라이트 테마), 오픈소스 엔진(F5-TTS / GPT-SoVITS) 사용.

## 빠른 시작 (새 컴퓨터 포함)

```powershell
# 1) 초기 세팅 — uv, Python 3.10, ffmpeg, PyTorch(GPU), 전처리, F5-TTS 자동 설치
.\setup.ps1

# 2) 실행 — 브라우저에서 GUI 가 열립니다 (http://127.0.0.1:7860)
.\run.ps1
```

### 세팅 옵션
| 명령 | 설명 |
|------|------|
| `.\setup.ps1` | 기본 — 앱 + ffmpeg + GPU PyTorch + 전처리 + F5-TTS |
| `.\setup.ps1 -Light` | GUI만 빠르게 (ML 제외, 화면 미리보기용) |
| `.\setup.ps1 -Cpu` | GPU 없이 CPU 실행 |
| `.\setup.ps1 -SoVITS` | GPT-SoVITS 까지 설치 |

## 사용 흐름
1. **목소리 학습** 탭 → 이름 + 유튜브 주소 입력 → `학습 시작`
   - 음성 추출(yt-dlp) → 배경음 제거(Demucs) → 문장 분할·자막(faster-whisper) → 학습
2. **음성 만들기** 탭 → 목소리 선택 → 텍스트 입력 → `생성하기`
3. **설정** 탭 → 엔진(F5-TTS/GPT-SoVITS), 연산 장치, 테마 변경

## 구조
```
app/           FastAPI 백엔드 + 정적 GUI (static/)
pipeline/      download → separate → segment → synth/train
data/voices/   학습된 목소리 등록 정보
outputs/       생성된 오디오
tools/ffmpeg/  번들 ffmpeg (setup 이 자동 배치)
engines/       GPT-SoVITS 등 외부 엔진 레포
```

## 한국어 목소리는 어떤 엔진?
- **GPT-SoVITS (한국어 주력 권장)** — 몇 분 분량의 목소리로 파인튜닝하며 한국어 텍스트 처리가 내장돼 있어, 한국어 목소리 복제 재현도가 가장 좋습니다. `.\setup.ps1 -SoVITS` 로 설치.
- **F5-TTS** — 제로샷 복제가 빠르고 쉽지만 **기본 모델이 영어/중국어 위주**입니다. 한국어로 쓰려면 한국어 파인튜닝 체크포인트를 구해 `config.json` 의 `f5.ckpt_file` 에 지정해야 합니다. (공식 유지 체크포인트는 아직 제한적)

> 요약: **한국어 = GPT-SoVITS**, 영어·일어·중국어 빠른 복제 = F5-TTS.

## 하드웨어 권장
- **학습·주 사용**: NVIDIA RTX 2060 Super(8GB) 이상 권장
- **추론만**: 6GB 이상이면 원활, 3GB(GTX 1060 3GB)는 모델·설정에 따라 제약
- GPU가 없으면 `-Cpu` (느림) 또는 클라우드 GPU 대여 후 학습만 수행

## ⚠️ 사용 주의
실존 인물의 목소리 복제는 **개인 학습·연구 용도**로만 사용하세요.
공개·상업적 사용은 당사자 동의 및 관련 법(초상권·저작권)을 확인해야 합니다.
