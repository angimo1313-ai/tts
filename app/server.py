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
        return updater.check_and_update()
    except Exception as e:
        raise HTTPException(500, f"업데이트 실패: {e}")


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
