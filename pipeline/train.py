"""Training orchestration — yields NDJSON-friendly progress events.

Each yielded dict may contain:
  {"step": <id>, "state": "start"|"done"}   -> updates the UI step chips
  {"msg": "..."}                             -> appends to the log
"""
from __future__ import annotations

import json
import traceback
from datetime import datetime
from pathlib import Path

from . import download


def _ev(**kw):
    return kw


def run(name: str, engine: str, device: str, voices_dir: Path, data_dir: Path,
        url: str | None = None, source_file: str | None = None, separate: bool = True):
    voice_id = _slug(name)
    vdir = voices_dir / voice_id
    raw_dir = data_dir / "raw" / voice_id
    dataset_dir = data_dir / "datasets" / voice_id
    vdir.mkdir(parents=True, exist_ok=True)

    try:
        # ---- 1. obtain source audio (YouTube download OR uploaded file) ----
        if source_file:
            yield _ev(step="download", state="start", msg="[1/4] 업로드 파일 변환")
            wav = download.convert_local(Path(source_file), raw_dir, "source")
        else:
            yield _ev(step="download", state="start", msg=f"[1/4] 유튜브 음성 추출: {url}")
            wav = download.download_audio(url, raw_dir, "source")
        yield _ev(step="download", state="done", msg=f"      완료 → {wav.name}")

        # ---- 2. separate (vocal isolation) — 깨끗한 업로드면 건너뜀 ----
        if not separate:
            vocals = wav
            yield _ev(step="separate", state="done", msg="[2/4] 배경음 제거 건너뜀 (깨끗한 음성)")
        else:
            yield _ev(step="separate", state="start", msg="[2/4] 배경음 제거 (Demucs)")
            try:
                from . import separate as sep_mod
                vocals = sep_mod.isolate_vocals(wav, raw_dir, device=device)
                yield _ev(step="separate", state="done", msg=f"      완료 → {vocals.name}")
            except ImportError:
                vocals = wav
                yield _ev(step="separate", state="done",
                          msg="      (Demucs 미설치 — 원본 음성 사용. setup 으로 설치 권장)")

        # ---- 3. segment + transcribe ----
        yield _ev(step="segment", state="start", msg="[3/4] 문장 분할·자막 (faster-whisper)")
        try:
            from . import segment
            n = segment.build_dataset(vocals, dataset_dir, device=device)
            yield _ev(step="segment", state="done", msg=f"      완료 → {n}개 구간")
        except ImportError:
            raise RuntimeError("전처리 스택(faster-whisper)이 설치되지 않았습니다. setup 을 먼저 실행하세요.")

        # ---- 4. train / register voice ----
        yield _ev(step="train", state="start", msg=f"[4/4] {engine.upper()} 학습")
        from . import synth
        result = synth.train_voice(voice_id=voice_id, name=name, dataset_dir=dataset_dir,
                                   engine=engine, device=device, out_dir=vdir)
        yield _ev(step="train", state="done", msg="      학습 완료")

        meta = {"id": voice_id, "name": name, "engine": engine,
                "created": datetime.now().isoformat(timespec="seconds"), **result}
        (vdir / "voice.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
        yield _ev(msg=f"✓ '{name}' 목소리가 등록되었습니다.")

    except Exception as e:
        yield _ev(msg="[오류] " + str(e))
        yield _ev(msg=traceback.format_exc())


def _slug(name: str) -> str:
    keep = [c if c.isalnum() or c in "-_" else "_" for c in name.strip()]
    s = "".join(keep).strip("_") or "voice"
    return s.lower()
