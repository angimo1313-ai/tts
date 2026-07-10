"""F5-TTS 런타임 스모크 테스트 — 모델 로드 + 추론 + wav 생성 확인."""
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import engine_f5  # noqa: E402

# 1) 내장 영어 예제 참조로 임시 목소리 등록
ref_src = ROOT / ".venv/Lib/site-packages/f5_tts/infer/examples/basic/basic_ref_en.wav"
vdir = ROOT / "data/voices/_smoke"
vdir.mkdir(parents=True, exist_ok=True)
shutil.copy(ref_src, vdir / "ref.wav")
(vdir / "ref.txt").write_text("Some call me nature, others call me mother nature.", encoding="utf-8")

# 2) 짧은 텍스트 생성
out = ROOT / "outputs/_smoke.wav"
out.parent.mkdir(exist_ok=True)
t0 = time.time()
print("generating…", flush=True)
res = engine_f5.generate(
    text="This is a smoke test of the Voice Studio text to speech system.",
    voice_dir=vdir, device="cuda", speed=1.0, out_path=out,
)
dt = time.time() - t0
size = res.stat().st_size
print(f"OK -> {res} ({size} bytes) in {dt:.1f}s", flush=True)
assert size > 1000, "출력 wav 가 비어 있습니다."
print("SMOKE PASS", flush=True)
