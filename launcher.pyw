"""Voice Studio 데스크톱 런처 — Chrome 앱 모드(프레임 없는 앱 창)로 실행.

.venv 의 pythonw.exe 로 실행되면 콘솔 없이:
  1) 로컬 서버(uvicorn)를 백그라운드로 기동
  2) HTTP 준비되면 Chrome(없으면 Edge) 앱 모드로 앱 창을 염 — 주소창/탭 없는 앱 창
  3) 창을 닫으면 서버도 함께 종료

Chrome/Edge 가 없으면 pywebview(WebView2) → 기본 브라우저 순으로 폴백.
"""
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PORT = 7860
URL = f"http://127.0.0.1:{PORT}"
CREATE_NO_WINDOW = 0x08000000


def http_ready() -> bool:
    try:
        with urllib.request.urlopen(URL + "/api/system", timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


def _msgbox(text: str):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, "Voice Studio", 0x10)
    except Exception:
        pass


def _find_browser():
    cands = [
        r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
        r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
        r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
        r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
        r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
    ]
    for c in cands:
        p = os.path.expandvars(c)
        if os.path.exists(p):
            return p
    return None


def _open_window():
    """웹 UI 를 pywebview 네이티브 창으로 연다 (직전 상태). 창을 닫으면 반환."""
    try:
        import webview
        webview.create_window("Voice Studio", URL, width=1180, height=860, min_size=(920, 640))
        webview.start()
        return
    except Exception:
        pass
    # 폴백: 기본 브라우저
    import webbrowser
    webbrowser.open(URL)
    while http_ready():
        time.sleep(2)


def main():
    py = ROOT / ".venv" / "Scripts" / "python.exe"
    if not py.exists():
        _msgbox("환경이 설치되지 않았습니다.\n먼저 '환경 설치'를 실행하세요.")
        return

    server = None
    if not http_ready():
        env = dict(os.environ, PYTHONUTF8="1")
        # 콘솔(cmd) 창이 안 뜨도록 pythonw.exe(창 없는 파이썬)로 서버 실행,
        # 출력은 로그 파일로. (python.exe 는 콘솔 앱이라 창이 뜰 수 있음)
        pyw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
        server_exe = str(pyw) if pyw.exists() else str(py)
        (ROOT / "data").mkdir(parents=True, exist_ok=True)
        log = open(ROOT / "data" / "server.log", "a", encoding="utf-8", errors="ignore")
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # 창 숨김
        server = subprocess.Popen(
            [server_exe, "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(PORT)],
            cwd=str(ROOT), creationflags=CREATE_NO_WINDOW, env=env,
            stdout=log, stderr=subprocess.STDOUT, startupinfo=si,
        )
    # 서버가 실제 HTTP 응답을 줄 때까지 대기(최대 60초) — 준비 후에만 창을 연다
    for _ in range(120):
        if http_ready():
            break
        if server is not None and server.poll() is not None:
            _msgbox("서버 시작에 실패했습니다.")
            return
        time.sleep(0.5)

    try:
        _open_window()
    finally:
        if server is not None and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except Exception:
                server.kill()


if __name__ == "__main__":
    main()
