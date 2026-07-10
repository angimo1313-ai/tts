"""Synthesis + per-engine voice registration.

Dispatches to the selected engine (F5-TTS / GPT-SoVITS). Engines are imported
lazily so a missing/uninstalled engine yields a clear message instead of a
server crash.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VOICES_DIR = ROOT / "data" / "voices"

# Make bundled ffmpeg visible to every engine/subprocess in this process.
_FFMPEG_BIN = ROOT / "tools" / "ffmpeg" / "bin"
if _FFMPEG_BIN.exists() and str(_FFMPEG_BIN) not in os.environ.get("PATH", ""):
    os.environ["PATH"] = str(_FFMPEG_BIN) + os.pathsep + os.environ.get("PATH", "")


def _resolve_device(device: str) -> str:
    if device != "cuda":
        return "cpu"
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


# ---------------- Generate ----------------
def generate(text: str, voice_id: str | None, engine: str, device: str,
             speed: float, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"tts_{engine}_{stamp}.wav"
    dev = _resolve_device(device)

    if not voice_id:
        raise RuntimeError("목소리를 먼저 선택하거나 학습해 주세요.")
    voice_dir = VOICES_DIR / voice_id
    if not voice_dir.exists():
        raise RuntimeError(f"목소리를 찾을 수 없습니다: {voice_id}")

    if engine == "f5":
        from . import engine_f5
        return engine_f5.generate(text, voice_dir, dev, speed, out_path)
    elif engine == "sovits":
        from . import engine_sovits
        return engine_sovits.generate(text, voice_dir, dev, speed, out_path)
    raise NotImplementedError(f"알 수 없는 엔진: {engine}")


# ---------------- Train / register ----------------
def train_voice(voice_id: str, name: str, dataset_dir: Path, engine: str,
                device: str, out_dir: Path) -> dict:
    dev = _resolve_device(device)
    if engine == "f5":
        from . import engine_f5
        return engine_f5.register(voice_id, dataset_dir, out_dir)
    elif engine == "sovits":
        from . import engine_sovits
        return engine_sovits.train(voice_id, dataset_dir, dev, out_dir)
    raise NotImplementedError(f"알 수 없는 엔진: {engine}")
