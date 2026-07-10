"""Step 2 — isolate vocals from music/noise using Demucs.

Removes background music so the trainer learns a clean single voice.
"""
from __future__ import annotations

import os
from pathlib import Path

_FFMPEG_BIN = Path(__file__).resolve().parent.parent / "tools" / "ffmpeg" / "bin"
if _FFMPEG_BIN.exists():
    os.environ["PATH"] = str(_FFMPEG_BIN) + os.pathsep + os.environ.get("PATH", "")


def isolate_vocals(wav: Path, out_dir: Path, device: str = "cuda") -> Path:
    """Run Demucs and return the isolated vocals wav."""
    import torch  # noqa: F401  (ensures torch present)
    from demucs.separate import main as demucs_main  # type: ignore

    dev = "cuda" if (device == "cuda" and _cuda_ok()) else "cpu"
    sep_root = out_dir / "separated"
    sep_root.mkdir(parents=True, exist_ok=True)

    # htdemucs: 2-stem (vocals / no_vocals) is enough and fast.
    demucs_main([
        "--two-stems", "vocals",
        "-n", "htdemucs",
        "-d", dev,
        "-o", str(sep_root),
        str(wav),
    ])

    vocals = sep_root / "htdemucs" / wav.stem / "vocals.wav"
    if not vocals.exists():
        raise RuntimeError("Demucs 결과(vocals.wav)를 찾을 수 없습니다.")
    return vocals


def _cuda_ok() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False
