"""GPT-SoVITS v2 파인튜닝 오케스트레이터 (.venv-sovits 에서 실행).

webui.py 의 학습 절차를 그대로 재현:
  1) 1-get-text (BERT 특징)
  2) 2-get-hubert-wav32k (SSL 특징 + 32k wav)
  3) 3-get-semantic (시맨틱 토큰)
  4) s2_train (SoVITS/음색)
  5) s1_train (GPT/운율)
결과 가중치 경로를 RESULT 로 출력.

사용: python finetune_worker.py '<json-args>'
  args: exp_name, list_path, wav_dir, epochs_s2, epochs_s1, batch_size, is_half
"""
import glob
import json
import os
import subprocess
import sys
from pathlib import Path

SOVITS_DIR = Path(__file__).resolve().parent / "GPT-SoVITS"
APP_ROOT = SOVITS_DIR.parent.parent          # 프로젝트 루트
FFMPEG_BIN = APP_ROOT / "tools" / "ffmpeg" / "bin"
os.chdir(SOVITS_DIR)  # 스크립트들은 cwd=GPT-SoVITS 루트를 가정
sys.path.insert(0, str(SOVITS_DIR))

PM = "GPT_SoVITS/pretrained_models"
BERT = f"{PM}/chinese-roberta-wwm-ext-large"
CNHUBERT = f"{PM}/chinese-hubert-base"
S2G = f"{PM}/gsv-v2final-pretrained/s2G2333k.pth"
S2D = f"{PM}/gsv-v2final-pretrained/s2D2333k.pth"
S1 = f"{PM}/gsv-v2final-pretrained/s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt"
S2CONFIG = "GPT_SoVITS/configs/s2.json"
PY = sys.executable


def ev(**k):
    print("EVENT " + json.dumps(k, ensure_ascii=False), flush=True)


def run(script_args, extra_env=None):
    env = dict(os.environ)
    # GPT-SoVITS 스크립트들이 text/module 등을 import 하려면 GPT_SoVITS 가 경로에 있어야 함
    env["PYTHONPATH"] = str(SOVITS_DIR) + os.pathsep + str(SOVITS_DIR / "GPT_SoVITS")
    if FFMPEG_BIN.exists():
        env["PATH"] = str(FFMPEG_BIN) + os.pathsep + env.get("PATH", "")
    env.setdefault("PYTHONUTF8", "1")
    # PyTorch 2.6+ 는 torch.load 기본값이 weights_only=True 라, 체크포인트에 들어있는
    # pathlib.WindowsPath 등을 로드하다 UnpicklingError 로 실패한다. 우리가 만든/공식
    # 체크포인트만 다루므로 예전 동작(weights_only=False)으로 강제한다.
    env["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] = "1"
    if extra_env:
        env.update({k: str(v) for k, v in extra_env.items()})
    p = subprocess.run([PY, "-s"] + script_args, env=env, cwd=str(SOVITS_DIR),
                       capture_output=True, text=True, encoding="utf-8", errors="ignore")
    if p.returncode != 0:
        tail = ((p.stdout or "") + "\n" + (p.stderr or "")).strip()[-1200:]
        raise RuntimeError(f"{script_args[0]} 실패 (exit {p.returncode})\n{tail}")


def main():
    args = json.loads(sys.argv[1])
    exp_name = args["exp_name"]
    list_path = args["list_path"]
    wav_dir = args["wav_dir"]
    epochs_s2 = int(args.get("epochs_s2", 8))
    epochs_s1 = int(args.get("epochs_s1", 15))
    batch = int(args.get("batch_size", 4))
    is_half = bool(args.get("is_half", True))

    opt_dir = f"logs/{exp_name}"
    os.makedirs(opt_dir, exist_ok=True)
    Path("TEMP").mkdir(exist_ok=True)
    # 최종 가중치 저장 폴더 — s2/s1 은 my_save(shutil.move) 로 저장하므로
    # 이 폴더들이 없으면 마지막에 FileNotFoundError 로 실패한다.
    os.makedirs("SoVITS_weights_v2", exist_ok=True)
    os.makedirs("GPT_weights_v2", exist_ok=True)

    # 리스트 파일 BOM 제거 — BOM 이 붙으면 첫 줄 wav 파일명 앞에 U+FEFF 가 끼어
    # ffmpeg 가 "Illegal byte sequence" 로 파일을 못 여는 문제를 방지한다.
    lp = Path(list_path)
    if lp.exists():
        lp.write_text(lp.read_text(encoding="utf-8-sig"), encoding="utf-8")

    common = {
        "inp_text": list_path, "inp_wav_dir": wav_dir, "exp_name": exp_name,
        "opt_dir": opt_dir, "is_half": str(is_half),
        "i_part": "0", "all_parts": "1", "_CUDA_VISIBLE_DEVICES": "0",
    }

    # ---- 1) get-text ----
    ev(step="text", state="start", msg="[1/5] 텍스트 특징 추출 (BERT)")
    run(["GPT_SoVITS/prepare_datasets/1-get-text.py"], {**common, "bert_pretrained_dir": BERT})
    _merge(opt_dir, "2-name2text-0.txt", "2-name2text.txt")
    ev(step="text", state="done")

    # ---- 2) get-hubert ----
    ev(step="hubert", state="start", msg="[2/5] 음성 특징 추출 (HuBERT)")
    run(["GPT_SoVITS/prepare_datasets/2-get-hubert-wav32k.py"],
        {**common, "cnhubert_base_dir": CNHUBERT,
         "sv_path": f"{PM}/sv/pretrained_eres2netv2w24s4ep4.ckpt"})
    ev(step="hubert", state="done")

    # ---- 3) get-semantic ----
    ev(step="semantic", state="start", msg="[3/5] 시맨틱 토큰 추출")
    run(["GPT_SoVITS/prepare_datasets/3-get-semantic.py"],
        {**common, "pretrained_s2G": S2G, "s2config_path": S2CONFIG})
    _merge(opt_dir, "6-name2semantic-0.tsv", "6-name2semantic.tsv")
    ev(step="semantic", state="done")

    # ---- 4) s2 train (SoVITS) ----
    ev(step="train_s2", state="start", msg="[4/5] SoVITS(음색) 학습")
    # 체크포인트 저장 폴더 미리 생성 — s2_train 은 shutil.move 로 저장하므로
    # 이 폴더가 없으면 FileNotFoundError 로 실패한다(webui.py 와 동일 처리).
    os.makedirs(f"{opt_dir}/logs_s2_v2", exist_ok=True)
    s2 = json.loads(Path(S2CONFIG).read_text(encoding="utf-8"))
    b2 = batch
    if not is_half:
        s2["train"]["fp16_run"] = False
        b2 = max(1, batch // 2)
    s2["train"].update({
        "batch_size": b2, "epochs": epochs_s2, "text_low_lr_rate": 0.4,
        "pretrained_s2G": S2G, "pretrained_s2D": S2D, "if_save_latest": True,
        "if_save_every_weights": True, "save_every_epoch": epochs_s2,
        "gpu_numbers": "0", "grad_ckpt": False, "lora_rank": 32,
    })
    s2["model"]["version"] = "v2"
    s2["data"]["exp_dir"] = s2["s2_ckpt_dir"] = opt_dir
    s2["save_weight_dir"] = "SoVITS_weights_v2"
    s2["name"] = exp_name
    s2["version"] = "v2"
    Path("TEMP/tmp_s2.json").write_text(json.dumps(s2), encoding="utf-8")
    run(["GPT_SoVITS/s2_train.py", "--config", "TEMP/tmp_s2.json"])
    ev(step="train_s2", state="done")

    # ---- 5) s1 train (GPT) ----
    ev(step="train_s1", state="start", msg="[5/5] GPT(운율) 학습")
    os.makedirs(f"{opt_dir}/logs_s1_v2", exist_ok=True)
    import yaml
    s1 = yaml.safe_load(Path("GPT_SoVITS/configs/s1longer-v2.yaml").read_text(encoding="utf-8"))
    b1 = batch
    if not is_half:
        s1["train"]["precision"] = "32"
        b1 = max(1, batch // 2)
    s1["train"].update({
        "batch_size": b1, "epochs": epochs_s1, "save_every_n_epoch": epochs_s1,
        "if_save_every_weights": True, "if_save_latest": True, "if_dpo": False,
        "half_weights_save_dir": "GPT_weights_v2", "exp_name": exp_name,
    })
    s1["pretrained_s1"] = S1
    s1["train_semantic_path"] = f"{opt_dir}/6-name2semantic.tsv"
    s1["train_phoneme_path"] = f"{opt_dir}/2-name2text.txt"
    s1["output_dir"] = f"{opt_dir}/logs_s1_v2"
    os.environ["_CUDA_VISIBLE_DEVICES"] = "0"
    os.environ["hz"] = "25hz"
    Path("TEMP/tmp_s1.yaml").write_text(yaml.dump(s1, default_flow_style=False), encoding="utf-8")
    run(["GPT_SoVITS/s1_train.py", "--config_file", "TEMP/tmp_s1.yaml"])
    ev(step="train_s1", state="done")

    # ---- 결과 가중치 수집 ----
    sv = sorted(glob.glob(f"SoVITS_weights_v2/{exp_name}_e*.pth"), key=os.path.getmtime)
    gp = sorted(glob.glob(f"GPT_weights_v2/{exp_name}-e*.ckpt"), key=os.path.getmtime)
    result = {
        "sovits": str((SOVITS_DIR / sv[-1]).resolve()) if sv else "",
        "gpt": str((SOVITS_DIR / gp[-1]).resolve()) if gp else "",
    }
    ev(step="done", msg="파인튜닝 완료", result=result)
    print("RESULT " + json.dumps(result, ensure_ascii=False), flush=True)


def _merge(opt_dir, part_name, out_name):
    part = Path(opt_dir) / part_name
    out = Path(opt_dir) / out_name
    if part.exists():
        out.write_text(part.read_text(encoding="utf-8"), encoding="utf-8")
        part.unlink()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        ev(step="error", msg=str(e))
        traceback.print_exc()
        sys.exit(1)
