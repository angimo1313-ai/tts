"""GPT-SoVITS korean.py 를 Windows(빌드도구 없음) 환경에 맞게 패치.

문제: 한국어 G2P(g2pk2)가 mecab 백엔드 eunjeon 을 요구하고, Windows 의 win_G2p
래퍼는 경로에 공백/한글이 있으면 eunjeon data 디렉토리 재구성을 시도한다. 우리는
kiwipiepy 기반 eunjeon shim 을 쓰므로 win_G2p 대신 표준 g2pk2 G2p 를 사용해야 한다.

해결: `    G2p = win_G2p` 한 줄을 주석 처리(멱등). 이미 패치됐으면 건너뜀."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
korean = ROOT / "engines/GPT-SoVITS/GPT_SoVITS/text/korean.py"

if not korean.exists():
    print("korean.py 없음 — GPT-SoVITS 클론을 먼저 하세요.")
    sys.exit(1)

src = korean.read_text(encoding="utf-8")
MARK = "# [Voice Studio] win_G2p 미사용"

if MARK in src:
    print("이미 패치됨.")
    sys.exit(0)

target = "\n    G2p = win_G2p"
if target not in src:
    print("경고: 예상한 'G2p = win_G2p' 패턴을 찾지 못함. 이미 다른 버전일 수 있음.")
    sys.exit(0)

patched = src.replace(
    target,
    "\n    pass  " + MARK + " (eunjeon=kiwipiepy shim + 표준 g2pk2)",
)
korean.write_text(patched, encoding="utf-8")
print("korean.py 패치 완료.")
