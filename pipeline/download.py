"""Step 1 — extract audio from a YouTube URL with yt-dlp (+ffmpeg)."""
from __future__ import annotations

import os
from pathlib import Path

# Prefer a bundled ffmpeg if present (tools/ffmpeg/bin), else rely on PATH.
_FFMPEG_BIN = Path(__file__).resolve().parent.parent / "tools" / "ffmpeg" / "bin"
if _FFMPEG_BIN.exists():
    os.environ["PATH"] = str(_FFMPEG_BIN) + os.pathsep + os.environ.get("PATH", "")


def download_audio(url: str, out_dir: Path, name: str) -> Path:
    """Download the best audio track and convert to 24kHz mono wav."""
    import yt_dlp  # type: ignore

    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{name}.wav"

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(out_dir / f"{name}.%(ext)s"),
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "wav"},
        ],
        # 24kHz mono is a good source rate for most TTS trainers.
        "postprocessor_args": ["-ar", "24000", "-ac", "1"],
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    if not target.exists():
        # yt-dlp may keep original ext; find the produced wav
        cands = list(out_dir.glob(f"{name}.wav"))
        if cands:
            target = cands[0]
        else:
            raise RuntimeError("음성 추출에 실패했습니다. URL 또는 ffmpeg 설치를 확인하세요.")
    return target


def convert_local(src: Path, out_dir: Path, name: str) -> Path:
    """Convert an uploaded audio file to 24kHz mono wav via ffmpeg."""
    import subprocess

    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{name}.wav"
    ffmpeg = _FFMPEG_BIN / "ffmpeg.exe" if _FFMPEG_BIN.exists() else Path("ffmpeg")
    cmd = [str(ffmpeg), "-y", "-i", str(src), "-ar", "24000", "-ac", "1", str(target)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not target.exists():
        raise RuntimeError(f"오디오 변환 실패: {proc.stderr[-400:]}")
    return target
