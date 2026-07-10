"""Step 3 — segment audio into sentence clips + transcripts.

Uses faster-whisper for Korean ASR with word/segment timestamps, then writes
per-clip wav files and a metadata list the TTS trainers consume.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_FFMPEG_BIN = ROOT / "tools" / "ffmpeg" / "bin"
if _FFMPEG_BIN.exists():
    os.environ["PATH"] = str(_FFMPEG_BIN) + os.pathsep + os.environ.get("PATH", "")

# Clip length limits (seconds) — TTS trainers prefer 2–12s single-sentence clips.
MIN_SEC = 2.0
MAX_SEC = 14.0
TARGET_SR = 24000

# 속도 옵션 (config.json > train)
try:
    _TRAIN = json.loads((ROOT / "config.json").read_text(encoding="utf-8")).get("train", {})
except Exception:
    _TRAIN = {}
MAX_TRANSCRIBE_SEC = float(_TRAIN.get("max_transcribe_sec", 180))  # 앞부분만 받아쓰기
WHISPER_MODEL = _TRAIN.get("whisper_model", "small")
MAX_CLIPS = int(_TRAIN.get("max_clips", 40))


def build_dataset(vocals: Path, dataset_dir: Path, device: str = "cuda") -> int:
    """Transcribe (앞부분 MAX_TRANSCRIBE_SEC 초만) + slice into clips.
    제로샷 학습엔 참조 클립만 필요하므로 전체가 아닌 앞부분만 처리해 속도를 높인다."""
    import soundfile as sf
    import librosa
    from faster_whisper import WhisperModel  # type: ignore

    dataset_dir.mkdir(parents=True, exist_ok=True)
    clips_dir = dataset_dir / "wavs"
    clips_dir.mkdir(exist_ok=True)

    dur_arg = MAX_TRANSCRIBE_SEC if MAX_TRANSCRIBE_SEC > 0 else None
    # 16kHz(whisper용) / 24kHz(클립용) 둘 다 앞부분만 로드
    audio16 = librosa.load(str(vocals), sr=16000, mono=True, duration=dur_arg)[0]
    audio, _ = librosa.load(str(vocals), sr=TARGET_SR, mono=True, duration=dur_arg)

    def _transcribe(dev: str):
        cands = ["float16", "int8_float16", "int8", "float32"] if dev == "cuda" else ["int8", "float32"]
        model = None
        last = None
        for ct in cands:
            try:
                model = WhisperModel(WHISPER_MODEL, device=dev, compute_type=ct)
                break
            except ValueError as e:
                last = e
        if model is None:
            raise RuntimeError(f"Whisper 모델 로드 실패: {last}")
        gen, _ = model.transcribe(audio16, language="ko", vad_filter=True,
                                  vad_parameters={"min_silence_duration_ms": 400})
        return list(gen)  # force execution here so CUDA errors surface now

    want_cuda = device == "cuda" and _cuda_ok()
    try:
        segments = _transcribe("cuda" if want_cuda else "cpu")
    except RuntimeError as e:
        # ctranslate2 needs CUDA12 libs; our stack is CUDA11 → fall back to CPU.
        if want_cuda and any(k in str(e).lower() for k in ("cublas", "cuda", "cudnn", "library")):
            segments = _transcribe("cpu")
        else:
            raise

    meta_lines = []
    idx = 0
    for seg in segments:
        if idx >= MAX_CLIPS:
            break  # 참조용으로 충분 — 조기 종료
        dur = seg.end - seg.start
        text = (seg.text or "").strip()
        if not text or dur < MIN_SEC or dur > MAX_SEC:
            continue
        a = int(seg.start * TARGET_SR)
        b = int(seg.end * TARGET_SR)
        clip = audio[a:b]
        if len(clip) < int(MIN_SEC * TARGET_SR):
            continue
        idx += 1
        fname = f"{idx:04d}.wav"
        sf.write(clips_dir / fname, clip, TARGET_SR)
        # metadata.csv format: wavs/0001.wav|텍스트
        meta_lines.append(f"wavs/{fname}|{text}")

    (dataset_dir / "metadata.csv").write_text("\n".join(meta_lines), encoding="utf-8")

    if idx == 0:
        raise RuntimeError("사용 가능한 음성 구간을 찾지 못했습니다. 더 또렷한 단일 화자 영상을 사용해 주세요.")
    return idx


def _cuda_ok() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False
