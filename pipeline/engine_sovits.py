"""GPT-SoVITS engine — Korean-first, high-fidelity zero-shot cloning.

GPT-SoVITS lives in its own venv (.venv-sovits) with its own dependency set,
so we run its bundled `api_v2.py` server as a persistent subprocess and talk to
it over HTTP. Models load once at server start; later requests are fast.

`register()` is zero-shot: it stores a clean reference clip + transcript (like
F5). Fine-tuning for even higher fidelity can be added later.
"""
from __future__ import annotations

import atexit
import json
import os
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
SOVITS_DIR = ROOT / "engines" / "GPT-SoVITS"
SOVITS_PY = ROOT / ".venv-sovits" / "Scripts" / "python.exe"
_CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
_CFG = _CONFIG.get("sovits", {})
PORT = int(_CFG.get("port", 9880))
_LOG_PATH = SOVITS_DIR / "sovits_server.log"

_server: subprocess.Popen | None = None


def _log_tail(n: int = 1800) -> str:
    try:
        return _LOG_PATH.read_text(encoding="utf-8", errors="ignore")[-n:] or "(로그 비어있음)"
    except Exception:
        return "(로그 파일 없음)"


# ---------------- config yaml ----------------
def _write_config() -> Path:
    """Write a tts_infer yaml pointing at v2 models with our device/is_half."""
    pm = "GPT_SoVITS/pretrained_models"
    device = _CFG.get("device", "auto")
    try:
        import torch
        has_cuda = torch.cuda.is_available()
    except Exception:
        has_cuda = False
    if device in ("auto", "cuda"):
        device = "cuda" if has_cuda else "cpu"
    # FP16 은 GPU 에서만 (CPU 는 미지원/무의미)
    is_half = bool(_CFG.get("is_half", True)) and device == "cuda"

    cfg = {
        "custom": {
            "bert_base_path": f"{pm}/chinese-roberta-wwm-ext-large",
            "cnhuhbert_base_path": f"{pm}/chinese-hubert-base",
            "device": device,
            "is_half": is_half,
            "version": "v2",
            "t2s_weights_path": f"{pm}/gsv-v2final-pretrained/s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt",
            "vits_weights_path": f"{pm}/gsv-v2final-pretrained/s2G2333k.pth",
        }
    }
    import yaml  # PyYAML present in sovits deps; also in main via fastapi extras
    out = SOVITS_DIR / "tts_infer_vs.yaml"
    out.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    return out


# ---------------- server lifecycle ----------------
def _port_open() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def _start_server(timeout: int = 300):
    global _server
    if _port_open():
        return
    if _server is not None and _server.poll() is None:
        pass
    else:
        if not SOVITS_PY.exists():
            raise RuntimeError("GPT-SoVITS venv 가 없습니다. `.\\setup.ps1 -SoVITS` 를 실행하세요.")
        cfg = _write_config()
        # fast_langdetect(언어 감지) 캐시 폴더가 없으면 tts 가 실패하므로 미리 생성.
        (SOVITS_DIR / "GPT_SoVITS" / "pretrained_models" / "fast_langdetect").mkdir(parents=True, exist_ok=True)
        cmd = [str(SOVITS_PY), "api_v2.py", "-a", "127.0.0.1", "-p", str(PORT),
               "-c", str(cfg.name)]
        # 서버 출력을 로그로 남겨 크래시 원인을 앱에서 볼 수 있게 한다.
        env = dict(os.environ, PYTHONUTF8="1")
        log_fh = open(_LOG_PATH, "w", encoding="utf-8", errors="ignore")
        # CMD 창이 안 뜨도록 콘솔 숨김
        CREATE_NO_WINDOW = 0x08000000
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        _server = subprocess.Popen(cmd, cwd=str(SOVITS_DIR), stdout=log_fh,
                                   stderr=subprocess.STDOUT, env=env,
                                   creationflags=CREATE_NO_WINDOW, startupinfo=si)
        atexit.register(_stop_server)

    # wait until the server accepts connections (models finished loading)
    t0 = time.time()
    while time.time() - t0 < timeout:
        if _server is not None and _server.poll() is not None:
            raise RuntimeError("GPT-SoVITS 서버가 시작 중 종료되었습니다.\n\n[로그]\n" + _log_tail())
        if _port_open():
            return
        time.sleep(1.0)
    raise RuntimeError("GPT-SoVITS 서버 시작 시간 초과.\n\n[로그]\n" + _log_tail())


def _stop_server():
    global _server
    if _server is not None and _server.poll() is None:
        _server.terminate()
        try:
            _server.wait(timeout=5)
        except Exception:
            _server.kill()
    _server = None


# ---------------- register (zero-shot) ----------------
def _pick_reference(dataset_dir: Path):
    meta = (dataset_dir / "metadata.csv").read_text(encoding="utf-8").strip().splitlines()
    best = None
    for line in meta:
        if "|" not in line:
            continue
        rel, text = line.split("|", 1)
        wav = dataset_dir / rel
        if not wav.exists():
            continue
        info = sf.info(str(wav))
        dur = info.frames / info.samplerate
        # GPT-SoVITS prefers a 3–10s reference; target ~6s.
        if 3.0 <= dur <= 10.0:
            score = -abs(dur - 6.0)
            if best is None or score > best[0]:
                best = (score, wav, text.strip())
    if best is None:  # fall back to any clip
        for line in meta:
            rel, text = line.split("|", 1)
            wav = dataset_dir / rel
            if wav.exists():
                return wav, text.strip()
        raise RuntimeError("참조 클립을 찾을 수 없습니다.")
    return best[1], best[2]


def train(voice_id: str, dataset_dir: Path, device: str, out_dir: Path) -> dict:
    ref_wav, ref_text = _pick_reference(dataset_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(ref_wav, out_dir / "ref.wav")
    (out_dir / "ref.txt").write_text(ref_text, encoding="utf-8")
    return {"ref_wav": "ref.wav", "ref_text": ref_text, "mode": "zero-shot", "lang": "ko"}


# ---------------- generate ----------------
def generate(text: str, voice_dir: Path, device: str, speed: float, out_path: Path,
             params: dict | None = None) -> Path:
    ref_wav = voice_dir / "ref.wav"
    ref_txt = voice_dir / "ref.txt"
    if not ref_wav.exists():
        raise RuntimeError("이 목소리의 참조 클립이 없습니다. 다시 학습해 주세요.")
    ref_text = ref_txt.read_text(encoding="utf-8").strip() if ref_txt.exists() else ""
    params = params or {}

    _start_server()

    payload = {
        "text": text,
        "text_lang": "ko",
        "ref_audio_path": str(ref_wav.resolve()),
        "prompt_text": ref_text,
        "prompt_lang": "ko",
        "text_split_method": "cut5",   # 장문을 문장 단위로 분할
        "speed_factor": float(speed),
        # 발음·톤 튜닝
        "temperature": float(params.get("temperature", 1.0)),
        "top_k": int(params.get("top_k", 15)),
        "top_p": float(params.get("top_p", 1.0)),
        "repetition_penalty": float(params.get("repetition_penalty", 1.35)),
        "media_type": "wav",
        "streaming_mode": False,
        # 장문 속도: 여러 문장을 병렬 배치로 처리
        "batch_size": int(_CFG.get("batch_size", 4)),
        "parallel_infer": True,
        "split_bucket": True,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/tts", data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            audio = resp.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GPT-SoVITS 생성 실패: {e.read().decode('utf-8', 'ignore')[:300]}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(audio)
    return out_path
