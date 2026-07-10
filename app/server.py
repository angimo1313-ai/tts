"""Voice Studio — FastAPI backend.

Serves the local GUI and orchestrates the voice-cloning pipeline:
  YouTube download -> vocal separation -> segmentation -> train/generate.

Heavy ML steps are imported lazily so the server runs (and the GUI loads)
even before the ML stack is installed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import shutil
import tempfile

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ---- Paths ----
ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
DATA = ROOT / "data"
VOICES_DIR = DATA / "voices"
OUTPUTS = ROOT / "outputs"
for d in (DATA, VOICES_DIR, OUTPUTS):
    d.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Voice Studio")


# ================= Models =================
class GenerateReq(BaseModel):
    text: str
    voice: str | None = None
    engine: str = "f5"
    device: str = "cuda"
    speed: float = 1.0
    # 발음·톤 튜닝(GPT-SoVITS)
    temperature: float = 1.0
    top_k: int = 15
    top_p: float = 1.0
    repetition_penalty: float = 1.35


class TrainReq(BaseModel):
    name: str
    url: str
    engine: str = "f5"
    device: str = "cuda"
    separate: bool = True


# ================= System info =================
@app.get("/api/system")
def system_info():
    info = {"python": sys.version.split()[0], "gpu": None, "cuda": None, "torch": None}
    try:
        import torch  # type: ignore
        info["torch"] = torch.__version__.split("+")[0]
        if torch.cuda.is_available():
            info["gpu"] = torch.cuda.get_device_name(0)
            info["cuda"] = torch.version.cuda
    except Exception:
        pass
    return info


# ================= Voice registry =================
def _load_voices() -> list[dict]:
    out = []
    for meta in sorted(VOICES_DIR.glob("*/voice.json")):
        try:
            out.append(json.loads(meta.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


@app.get("/api/voices")
def list_voices():
    return _load_voices()


# ================= Generate =================
@app.post("/api/generate")
def generate(req: GenerateReq):
    if not req.text.strip():
        raise HTTPException(400, "빈 텍스트입니다.")
    try:
        from pipeline import synth  # lazy import
    except Exception as e:
        raise HTTPException(503, f"TTS 엔진이 아직 설치되지 않았습니다. setup 을 완료해 주세요. ({e})")

    try:
        out_path = synth.generate(
            text=req.text, voice_id=req.voice, engine=req.engine,
            device=req.device, speed=req.speed, out_dir=OUTPUTS,
            params={"temperature": req.temperature, "top_k": req.top_k,
                    "top_p": req.top_p, "repetition_penalty": req.repetition_penalty},
        )
    except NotImplementedError as e:
        raise HTTPException(501, str(e))
    except Exception as e:
        raise HTTPException(500, f"생성 실패: {e}")

    rel = out_path.name
    entry = _record_history(out_path, req)
    return {"url": f"/outputs/{rel}", "entry": entry}


# ================= History (보관함) =================
HISTORY_FILE = OUTPUTS / "history.jsonl"


def _voice_name(voice_id: str | None) -> str:
    if not voice_id:
        return "-"
    meta = VOICES_DIR / voice_id / "voice.json"
    if meta.exists():
        try:
            return json.loads(meta.read_text(encoding="utf-8")).get("name", voice_id)
        except Exception:
            pass
    return voice_id


def _record_history(out_path: Path, req: GenerateReq) -> dict:
    from datetime import datetime
    entry = {
        "file": out_path.name,
        "url": f"/outputs/{out_path.name}",
        "text": req.text,
        "voice": req.voice,
        "voice_name": _voice_name(req.voice),
        "engine": req.engine,
        "speed": req.speed,
        "created": datetime.now().isoformat(timespec="seconds"),
        "size": out_path.stat().st_size if out_path.exists() else 0,
    }
    with HISTORY_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


@app.get("/api/history")
def get_history():
    if not HISTORY_FILE.exists():
        return []
    out = []
    for line in HISTORY_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except Exception:
            continue
        # 파일이 실제 존재하는 항목만 (수동 삭제된 것은 제외)
        if (OUTPUTS / e.get("file", "")).exists():
            out.append(e)
    out.reverse()  # 최신순
    return out


class DeleteReq(BaseModel):
    file: str


@app.post("/api/history/delete")
def delete_history(req: DeleteReq):
    # 명시적 삭제만 — 자동 삭제 없음
    name = Path(req.file).name  # path traversal 방지
    target = OUTPUTS / name
    if target.exists() and target.suffix == ".wav":
        target.unlink()
    # jsonl 에서 해당 항목 제거
    if HISTORY_FILE.exists():
        kept = [ln for ln in HISTORY_FILE.read_text(encoding="utf-8").splitlines()
                if ln.strip() and json.loads(ln).get("file") != name]
        HISTORY_FILE.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    return {"ok": True}


@app.post("/api/download")
def download_to_downloads(req: DeleteReq):
    """pywebview(WebView2)에서는 <a download> 가 안 되므로, 파일을 사용자
    Downloads 폴더에 복사해 준다."""
    import os
    name = Path(req.file).name
    src = OUTPUTS / name
    if not src.exists():
        raise HTTPException(404, "파일을 찾을 수 없습니다.")
    downloads = Path(os.path.expanduser("~")) / "Downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    dst = downloads / name
    # 같은 이름 있으면 번호 붙이기
    if dst.exists():
        stem, suf = dst.stem, dst.suffix
        i = 1
        while (downloads / f"{stem}_{i}{suf}").exists():
            i += 1
        dst = downloads / f"{stem}_{i}{suf}"
    shutil.copy(src, dst)
    return {"saved": str(dst), "name": dst.name}


# ================= Voices (목소리 관리) =================
class VoiceDeleteReq(BaseModel):
    id: str


@app.post("/api/voices/delete")
def delete_voice(req: VoiceDeleteReq):
    vid = Path(req.id).name  # traversal 방지
    vdir = VOICES_DIR / vid
    if not vdir.exists():
        raise HTTPException(404, "목소리를 찾을 수 없습니다.")
    shutil.rmtree(vdir, ignore_errors=True)
    # 누적 데이터셋도 정리
    for d in ((DATA / "datasets" / vid), (DATA / "raw" / vid)):
        shutil.rmtree(d, ignore_errors=True)
    return {"ok": True}


@app.post("/api/open-outputs")
def open_outputs():
    import subprocess
    try:
        subprocess.Popen(["explorer.exe", str(OUTPUTS)])
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"ok": True}


# ================= Train (streaming NDJSON) =================
@app.post("/api/train")
def train(req: TrainReq):
    try:
        from pipeline import train as train_mod  # lazy import
    except Exception as e:
        raise HTTPException(503, f"학습 파이프라인을 불러올 수 없습니다. ({e})")

    def stream():
        for event in train_mod.run(name=req.name, url=req.url, engine=req.engine,
                                   device=req.device, voices_dir=VOICES_DIR, data_dir=DATA,
                                   separate=req.separate):
            yield json.dumps(event, ensure_ascii=False) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@app.post("/api/train_upload")
async def train_upload(
    file: UploadFile = File(...),
    name: str = Form(...),
    engine: str = Form("f5"),
    device: str = Form("cuda"),
    separate: bool = Form(False),
):
    try:
        from pipeline import train as train_mod
    except Exception as e:
        raise HTTPException(503, f"학습 파이프라인을 불러올 수 없습니다. ({e})")

    # persist upload to a temp file the pipeline can read
    suffix = Path(file.filename or "audio").suffix or ".bin"
    tmp = Path(tempfile.gettempdir()) / f"vs_upload_{name}{suffix}"
    with tmp.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    def stream():
        try:
            for event in train_mod.run(name=name, engine=engine, device=device,
                                       voices_dir=VOICES_DIR, data_dir=DATA,
                                       source_file=str(tmp), separate=separate):
                yield json.dumps(event, ensure_ascii=False) + "\n"
        finally:
            tmp.unlink(missing_ok=True)

    return StreamingResponse(stream(), media_type="application/x-ndjson")


# ================= Fine-tuning (누적 정밀 학습) =================
class FinetuneReq(BaseModel):
    voice: str
    epochs_s2: int = 8
    epochs_s1: int = 15
    batch_size: int = 4


@app.post("/api/finetune")
def finetune(req: FinetuneReq):
    vid = Path(req.voice).name
    vdir = VOICES_DIR / vid
    dataset_dir = DATA / "datasets" / vid
    if not vdir.exists():
        raise HTTPException(404, "목소리를 찾을 수 없습니다.")
    if not (dataset_dir / "metadata.csv").exists():
        raise HTTPException(400, "학습 데이터가 없습니다. 먼저 음성을 추가하세요.")
    try:
        from pipeline import engine_sovits
    except Exception as e:
        raise HTTPException(503, f"GPT-SoVITS 환경을 불러올 수 없습니다. ({e})")

    def stream():
        try:
            for event in engine_sovits.finetune(
                vid, vid, dataset_dir, vdir,
                epochs_s2=req.epochs_s2, epochs_s1=req.epochs_s1, batch_size=req.batch_size,
            ):
                yield json.dumps(event, ensure_ascii=False) + "\n"
        except Exception as e:
            yield json.dumps({"step": "error", "msg": str(e)}, ensure_ascii=False) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@app.get("/api/dataset-info")
def dataset_info(voice: str):
    vid = Path(voice).name
    meta = DATA / "datasets" / vid / "metadata.csv"
    n = 0
    if meta.exists():
        n = len([l for l in meta.read_text(encoding="utf-8").splitlines() if "|" in l])
    vf = VOICES_DIR / vid / "voice.json"
    mode = "zero-shot"
    if vf.exists():
        try:
            mode = json.loads(vf.read_text(encoding="utf-8")).get("mode", "zero-shot")
        except Exception:
            pass
    return {"clips": n, "mode": mode}


# ================= Update (GitHub API, git 불필요) =================
class TokenReq(BaseModel):
    token: str


@app.get("/api/github-token")
def github_token_status():
    from app import updater
    return {"set": updater.has_token()}


@app.post("/api/github-token")
def save_github_token(req: TokenReq):
    from app import updater
    updater.set_token(req.token)
    return {"ok": True, "set": updater.has_token()}


@app.post("/api/update")
def do_update():
    from app import updater
    try:
        result = updater.check_and_update()
    except Exception as e:
        raise HTTPException(500, f"업데이트 실패: {e}")
    if result.get("updated"):
        _schedule_restart()
        result["message"] = "새 버전을 적용했습니다. 잠시 후 앱이 자동으로 재시작됩니다."
    return result


@app.post("/api/restart")
def restart_app():
    _schedule_restart()
    return {"ok": True}


def _schedule_restart():
    """분리된 프로세스로 앱을 껐다 켠다(자동 재시작). 응답이 나간 뒤 실행되도록 지연."""
    import subprocess
    pyw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
    launcher = ROOT / "launcher.pyw"
    if not pyw.exists():
        return
    ps = (
        "Start-Sleep -Seconds 2; "
        "Get-Process pythonw,python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue; "
        "Start-Sleep -Seconds 1; "
        f"Start-Process '{pyw}' -ArgumentList 'launcher.pyw' -WorkingDirectory '{ROOT}'"
    )
    DETACHED = 0x00000008
    subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                     creationflags=DETACHED)


# ================= Static / outputs =================
@app.get("/outputs/{name}")
def serve_output(name: str):
    p = OUTPUTS / name
    if not p.exists():
        raise HTTPException(404, "파일 없음")
    return FileResponse(p)


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.server:app", host="127.0.0.1", port=7860, reload=False)
