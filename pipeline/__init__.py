"""Voice-cloning pipeline: download -> separate -> segment -> train/synth."""
import os
from pathlib import Path

# Bundled ffmpeg on PATH (yt-dlp, demucs, pydub all look it up there).
_FFMPEG_BIN = Path(__file__).resolve().parent.parent / "tools" / "ffmpeg" / "bin"
if _FFMPEG_BIN.exists() and str(_FFMPEG_BIN) not in os.environ.get("PATH", ""):
    os.environ["PATH"] = str(_FFMPEG_BIN) + os.pathsep + os.environ.get("PATH", "")

# Quieter HF cache logging on Windows (no symlink support without dev mode).
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
