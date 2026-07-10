"""Voice Studio 데스크톱 런처.

.venv 의 pythonw.exe 로 실행되면 콘솔 창 없이:
  1) 로컬 서버(uvicorn)를 백그라운드로 기동
  2) 준비되면 기본 브라우저로 앱을 염
  3) 이 창(트레이 없이 조용히 대기)이 살아있는 동안 서버 유지

바로가기(.lnk)가 이 파일을 pythonw 로 가리킨다. (scripts/make_shortcut.ps1)
"""
import os
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PORT = 7860
URL = f"http://127.0.0.1:{PORT}"

CREATE_NO_WINDOW = 0x08000000  # 서버 서브프로세스도 콘솔 없이


def port_open() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def main():
    py = ROOT / ".venv" / "Scripts" / "python.exe"
    if not py.exists():
        # 환경 미설치 → 안내 (콘솔 없이 메시지 박스)
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0, "환경이 설치되지 않았습니다.\n먼저 setup.ps1 을 실행하세요.", "Voice Studio", 0x10)
        return

    if not port_open():
        env = dict(os.environ, PYTHONUTF8="1")
        subprocess.Popen(
            [str(py), "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(PORT)],
            cwd=str(ROOT), creationflags=CREATE_NO_WINDOW, env=env,
        )
        # 서버 준비 대기 (최대 40초)
        for _ in range(80):
            if port_open():
                break
            time.sleep(0.5)

    webbrowser.open(URL)

    # 서버가 떠 있는 동안 런처 유지 (닫으면 서버는 콘솔세션 종료와 함께 정리)
    try:
        while port_open():
            time.sleep(2)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
