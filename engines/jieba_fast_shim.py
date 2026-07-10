"""Shim: jieba_fast → jieba (API 호환). GPT-SoVITS 중국어 모듈이 요구하지만
컴파일이 필요해 Windows(빌드도구 없음)에서 설치 불가하므로 순수 파이썬 jieba 로 대체.
한국어 추론에는 실제로 호출되지 않음. setup.ps1 이 .venv-sovits 의 site-packages/jieba_fast/__init__.py 로 복사."""
import sys as _sys
import jieba as _jieba
import jieba.posseg as _posseg
import jieba.analyse as _analyse

for _k in dir(_jieba):
    if not _k.startswith("__"):
        globals()[_k] = getattr(_jieba, _k)

posseg = _posseg
analyse = _analyse
_sys.modules[__name__ + ".posseg"] = _posseg
_sys.modules[__name__ + ".analyse"] = _analyse
