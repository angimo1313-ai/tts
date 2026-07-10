"""업로드→전처리(segment)→F5 등록→생성 전체 흐름 스모크 테스트."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import train as train_mod  # noqa: E402
from pipeline import synth  # noqa: E402

src = ROOT / "outputs/_smoke.wav"  # 앞선 F5 스모크 출력(영어 음성)을 업로드본으로 사용
assert src.exists(), "먼저 smoke_f5.py 를 실행하세요."

print("=== train.run (upload, separate=False) ===", flush=True)
for ev in train_mod.run(name="uptest", engine="f5", device="cuda",
                        voices_dir=ROOT / "data/voices", data_dir=ROOT / "data",
                        source_file=str(src), separate=False):
    if ev.get("msg"):
        print(ev["msg"], flush=True)

print("=== generate with registered voice ===", flush=True)
out = synth.generate(text="The quick brown fox jumps over the lazy dog.",
                     voice_id="uptest", engine="f5", device="cuda", speed=1.0,
                     out_dir=ROOT / "outputs")
print(f"OK -> {out} ({out.stat().st_size} bytes)", flush=True)
print("UPLOAD SMOKE PASS", flush=True)
