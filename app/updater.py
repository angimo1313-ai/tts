"""앱 내 업데이트 — GitHub API 로 최신 코드를 받아 적용 (git 불필요).

비공개 저장소이므로 개인 액세스 토큰(PAT)이 필요하다. 토큰은 로컬
data/.github_token 에만 저장(깃 무시). 업데이트는 소스 파일만 덮어쓰고
가상환경/모델/목소리/생성물/사용자 config 는 건드리지 않는다.
"""
from __future__ import annotations

import json
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
# 토큰은 앱 폴더의 github_token.txt 에 직접 넣어도 되고(권장), 설정에서 저장해도 된다.
TOKEN_FILE = ROOT / "github_token.txt"
VERSION_FILE = DATA / ".version"

# 업데이트로 덮어쓰지 않을 것 (사용자 설정/데이터 보존)
SKIP_FILES = {"config.json"}
SKIP_TOP = {".venv", ".venv-sovits", ".uvhome", "engines", "tools", "data", "outputs", "models", ".git"}


def _cfg():
    c = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    u = c.get("update", {})
    return u.get("owner", "angimo1313-ai"), u.get("repo", "tts"), u.get("branch", "main")


def get_token() -> str:
    return TOKEN_FILE.read_text(encoding="utf-8").strip() if TOKEN_FILE.exists() else ""


def set_token(t: str):
    DATA.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text((t or "").strip(), encoding="utf-8")


def has_token() -> bool:
    return bool(get_token())


def _open(url: str, token: str = ""):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "VoiceStudio-Updater"}
    if token:  # 비공개 저장소용(공개면 없어도 됨)
        headers["Authorization"] = f"token {token}"
    req = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(req, timeout=120)


def check_and_update() -> dict:
    token = get_token()  # 공개 저장소면 없어도 동작
    owner, repo, branch = _cfg()
    try:
        with _open(f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}", token) as r:
            latest = json.loads(r.read().decode("utf-8"))["sha"]
    except Exception as e:
        return {"ok": False, "message": f"업데이트 확인 실패 (네트워크/저장소 공개 여부 확인): {e}"}

    current = VERSION_FILE.read_text(encoding="utf-8").strip() if VERSION_FILE.exists() else ""
    if latest == current:
        return {"ok": True, "updated": False, "message": "이미 최신 버전입니다.", "version": latest[:7]}

    try:
        tar_url = f"https://api.github.com/repos/{owner}/{repo}/tarball/{branch}"
        tmp = Path(tempfile.gettempdir()) / "vs_update.tar.gz"
        with _open(tar_url, token) as r, tmp.open("wb") as f:
            shutil.copyfileobj(r, f)
        n = _apply_tarball(tmp)
        tmp.unlink(missing_ok=True)
    except Exception as e:
        return {"ok": False, "message": f"업데이트 적용 실패: {e}"}

    VERSION_FILE.write_text(latest, encoding="utf-8")
    return {"ok": True, "updated": True, "files": n,
            "message": f"새 버전을 적용했습니다 ({n}개 파일). 앱을 껐다 켜면 반영됩니다.",
            "version": latest[:7]}


def _apply_tarball(tar_path: Path) -> int:
    count = 0
    with tarfile.open(tar_path, "r:gz") as tf:
        members = tf.getmembers()
        prefix = (members[0].name.split("/")[0] + "/") if members else ""
        for m in members:
            if not m.isfile():
                continue
            rel = m.name[len(prefix):] if m.name.startswith(prefix) else m.name
            if not rel or ".." in rel or rel.startswith("/"):
                continue
            top = rel.split("/")[0]
            if top in SKIP_TOP or rel in SKIP_FILES:
                continue
            dst = ROOT / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            f = tf.extractfile(m)
            if f is None:
                continue
            with f, dst.open("wb") as out:
                shutil.copyfileobj(f, out)
            count += 1
    return count
