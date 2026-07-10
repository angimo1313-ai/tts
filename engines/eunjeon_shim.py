"""Shim: eunjeon(mecab-ko) → kiwipiepy. GPT-SoVITS 의 한국어 G2P(g2pk2)가
형태소 분석기 eunjeon.Mecab 을 요구하지만 eunjeon 은 C++ 컴파일러가 필요하다.
컴파일러가 없어도 되는 순수 파이썬 kiwipiepy 로 동일 인터페이스(pos/morphs/nouns)를 제공.

g2pk2 는 mecab.pos(text) → [(형태소, 품사태그)] 만 사용하며, 형태소가 원문을
재구성하지 못하면 주석 없이 평문으로 처리하므로(안전 폴백) 품사 태그가 완벽히
같지 않아도 동작한다. kiwi 와 mecab-ko 는 둘 다 세종 태그셋 기반이라 대체로 호환.
setup.ps1 이 .venv-sovits/Lib/site-packages/eunjeon/__init__.py 로 복사."""
from kiwipiepy import Kiwi as _Kiwi

_kiwi = _Kiwi()


class Mecab:
    def __init__(self, *args, **kwargs):
        pass

    def pos(self, text):
        return [(t.form, t.tag) for t in _kiwi.tokenize(text)]

    def morphs(self, text):
        return [t.form for t in _kiwi.tokenize(text)]

    def nouns(self, text):
        return [t.form for t in _kiwi.tokenize(text) if t.tag.startswith("NN")]
