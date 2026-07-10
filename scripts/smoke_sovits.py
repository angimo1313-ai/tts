"""GPT-SoVITS 한국어 생성 스모크 테스트 (api_v2 서버 기동 + 추론)."""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import engine_sovits  # noqa: E402

voice_dir = ROOT / "data/voices/uptest"  # 앞선 업로드 스모크에서 등록된 참조 사용
assert (voice_dir / "ref.wav").exists(), "먼저 smoke_upload.py 로 목소리를 등록하세요."

text = "안녕하세요. 지금부터 음성 합성 테스트를 시작합니다. 긴 문장도 문장 단위로 자연스럽게 이어서 읽어 드립니다."
out = ROOT / "outputs/_sovits_smoke.wav"

t0 = time.time()
print("SoVITS 서버 기동 + 한국어 생성 중… (최초 모델 로딩으로 수분 소요)", flush=True)
res = engine_sovits.generate(text=text, voice_dir=voice_dir, device="cpu", speed=1.0, out_path=out)
print(f"OK -> {res} ({res.stat().st_size} bytes) in {time.time()-t0:.1f}s", flush=True)
assert res.stat().st_size > 5000, "출력이 비어 있습니다."
print("SOVITS SMOKE PASS", flush=True)
