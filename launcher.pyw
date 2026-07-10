"""Voice Studio 데스크톱 런처 — 독립 프로그램 창으로 실행.

.venv 의 pythonw.exe 로 실행되면 콘솔 없이:
  1) 로컬 서버(uvicorn)를 백그라운드로 기동
  2) 준비되면 네이티브 창(pywebview)으로 앱을 염 (브라우저 아님)
  3) 창을 닫으면 서버도 함께 종료

pywebview 가 없거나 실패하면 기본 브라우저로 폴백.
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


def port_open() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def http_ready() -> bool:
    # 서버가 실제로 HTTP 응답을 줄 때만 True (창이 일찍 열려 '연결 거부' 뜨는 것 방지)
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


def main():
    py = ROOT / ".venv" / "Scripts" / "python.exe"
    if not py.exists():
        _msgbox("환경이 설치되지 않았습니다.\n먼저 '환경 설치'를 실행하세요.")
        return

    server = None
    if not http_ready():
        env = dict(os.environ, PYTHONUTF8="1")
        server = subprocess.Popen(
            [str(py), "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(PORT)],
            cwd=str(ROOT), creationflags=CREATE_NO_WINDOW, env=env,
        )
    # 서버가 실제 HTTP 응답을 줄 때까지 대기 (최대 60초) — 준비 후에만 창을 연다
    for _ in range(120):
        if http_ready():
            break
        if server is not None and server.poll() is not None:
            _msgbox("서버 시작에 실패했습니다.")
            return
        time.sleep(0.5)

    try:
        # 네이티브 창 (Windows: Edge WebView2)
        import webview
        webview.create_window("Voice Studio", URL, width=1160, height=840,
                              min_size=(900, 640))
        webview.start()  # 창이 닫힐 때까지 블록
    except Exception:
        # 폴백: 기본 브라우저
        import webbrowser
        webbrowser.open(URL)
        try:
            while port_open():
                time.sleep(2)
        except KeyboardInterrupt:
            pass
    finally:
        if server is not None and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except Exception:
                server.kill()


if __name__ == "__main__":
    main()
