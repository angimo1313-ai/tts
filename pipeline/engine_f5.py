"""F5-TTS engine — zero-shot voice cloning + long-form synthesis.

F5-TTS clones a voice from a short reference clip (+its transcript), so
"training" here just selects and stores a clean reference from the dataset.
Generation feeds long text to F5-TTS, which chunks it internally for natural
long-form output.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
_CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

_MODEL = None  # cached F5TTS instance
_MODEL_DEVICE = None


def _get_model(device: str):
    global _MODEL, _MODEL_DEVICE
    if _MODEL is not None and _MODEL_DEVICE == device:
        return _MODEL
    from f5_tts.api import F5TTS  # type: ignore

    cfg = _CONFIG.get("f5", {})
    kwargs = {"device": device}
    if cfg.get("model_name"):
        kwargs["model"] = cfg["model_name"]
    if cfg.get("ckpt_file"):
        kwargs["ckpt_file"] = cfg["ckpt_file"]
    if cfg.get("vocab_file"):
        kwargs["vocab_file"] = cfg["vocab_file"]
    _MODEL = F5TTS(**kwargs)
    _MODEL_DEVICE = device
    return _MODEL


# ---------------- register (zero-shot) ----------------
def register(voice_id: str, dataset_dir: Path, out_dir: Path) -> dict:
    """Pick the best reference clip + transcript and store it in the voice dir."""
    meta = (dataset_dir / "metadata.csv").read_text(encoding="utf-8").strip().splitlines()
    if not meta:
        raise RuntimeError("데이터셋이 비어 있습니다.")

    # choose a mid-length clip (most stable reference, ~6–10s ideal)
    best = None
    for line in meta:
        rel, text = line.split("|", 1)
        wav = dataset_dir / rel
        if not wav.exists():
            continue
        info = sf.info(str(wav))
        dur = info.frames / info.samplerate
        score = -abs(dur - 8.0)  # closest to 8s wins
        if best is None or score > best[0]:
            best = (score, wav, text.strip())
    if best is None:
        raise RuntimeError("참조 클립을 찾을 수 없습니다.")

    _, ref_wav, ref_text = best
    out_dir.mkdir(parents=True, exist_ok=True)
    ref_dst = out_dir / "ref.wav"
    shutil.copy(ref_wav, ref_dst)
    (out_dir / "ref.txt").write_text(ref_text, encoding="utf-8")
    return {"ref_wav": "ref.wav", "ref_text": ref_text, "mode": "zero-shot"}


# ---------------- generate ----------------
def generate(text: str, voice_dir: Path, device: str, speed: float, out_path: Path) -> Path:
    ref_wav = voice_dir / "ref.wav"
    ref_txt = voice_dir / "ref.txt"
    if not ref_wav.exists():
        raise RuntimeError("이 목소리의 참조 클립이 없습니다. 다시 학습해 주세요.")
    ref_text = ref_txt.read_text(encoding="utf-8").strip() if ref_txt.exists() else ""

    def _infer(dev):
        m = _get_model(dev)
        return m.infer(ref_file=str(ref_wav), ref_text=ref_text, gen_text=text,
                       speed=speed, remove_silence=True)
    try:
        wav, sr, _ = _infer(device)
    except (RuntimeError, OSError) as e:
        # 3GB/older GPUs hit OOM or cuDNN/cuBLAS symbol errors → fall back to CPU.
        cuda_issue = any(k in str(e).lower() for k in
                         ("out of memory", "cudnn", "cublas", "cuda", "symbol"))
        if device == "cuda" and cuda_issue:
            wav, sr, _ = _infer("cpu")
        else:
            raise

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), wav, sr)
    return out_path
