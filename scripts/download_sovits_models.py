"""GPT-SoVITS v2 사전학습 모델 다운로드 (한국어 추론용 최소 세트).
간헐적 DNS 실패에 대비해 파일별 재시도 + 존재 검증."""
import os
import time
from pathlib import Path
from huggingface_hub import hf_hub_download

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

ROOT = Path(__file__).resolve().parent.parent
dst = ROOT / "engines/GPT-SoVITS/GPT_SoVITS/pretrained_models"
dst.mkdir(parents=True, exist_ok=True)

REPO = "lj1995/GPT-SoVITS"
FILES = [
    "chinese-hubert-base/config.json",
    "chinese-hubert-base/preprocessor_config.json",
    "chinese-hubert-base/pytorch_model.bin",
    "chinese-roberta-wwm-ext-large/config.json",
    "chinese-roberta-wwm-ext-large/tokenizer.json",
    "chinese-roberta-wwm-ext-large/pytorch_model.bin",
    "gsv-v2final-pretrained/s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt",
    "gsv-v2final-pretrained/s2G2333k.pth",
    "gsv-v2final-pretrained/s2D2333k.pth",  # 파인튜닝(학습) 초기화용 discriminator
]


def get(fname, tries=8):
    for i in range(tries):
        try:
            hf_hub_download(repo_id=REPO, filename=fname, local_dir=str(dst))
            return True
        except Exception as e:
            print(f"  retry {i+1}/{tries} {fname}: {type(e).__name__}", flush=True)
            time.sleep(4)
    return False


ok = True
for f in FILES:
    print("downloading", f, flush=True)
    if not get(f):
        print("  FAILED", f, flush=True)
        ok = False

# 검증
missing = [f for f in FILES if not (dst / f).exists()]
if missing or not ok:
    print("MISSING:", missing, flush=True)
    raise SystemExit(1)
print("SOVITS MODELS DONE", flush=True)
