"""Voice Studio — 네이티브 데스크톱 앱 (PySide6). 웹뷰/브라우저 없이 진짜 위젯 GUI.

기존 파이프라인(pipeline.*)을 직접 호출한다. 긴 작업은 QThread 로 실행해 UI가
멈추지 않게 한다.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt, QThread, Signal, QObject, QUrl
from PySide6.QtGui import QIcon
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QTextEdit, QSlider, QLineEdit, QCheckBox,
    QFileDialog, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
    QProgressBar, QGroupBox, QFormLayout, QSizePolicy,
)

DATA = ROOT / "data"
VOICES_DIR = DATA / "voices"
OUTPUTS = ROOT / "outputs"
for d in (DATA, VOICES_DIR, OUTPUTS):
    d.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    try:
        return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def list_voices() -> list[dict]:
    out = []
    for meta in sorted(VOICES_DIR.glob("*/voice.json")):
        try:
            out.append(json.loads(meta.read_text(encoding="utf-8")))
        except Exception:
            pass
    return out


# ------------------------------------------------------------------ workers
class GenWorker(QObject):
    done = Signal(str)      # out path
    failed = Signal(str)

    def __init__(self, text, voice_id, speed, params):
        super().__init__()
        self.text, self.voice_id, self.speed, self.params = text, voice_id, speed, params

    def run(self):
        try:
            from pipeline import synth
            out = synth.generate(text=self.text, voice_id=self.voice_id, engine="sovits",
                                 device="cuda", speed=self.speed, out_dir=OUTPUTS, params=self.params)
            self.done.emit(str(out))
        except Exception as e:
            self.failed.emit(str(e))


class StreamWorker(QObject):
    """train/finetune 처럼 이벤트를 yield 하는 제너레이터를 실행."""
    event = Signal(dict)
    finished = Signal(bool)   # success

    def __init__(self, gen_factory):
        super().__init__()
        self.gen_factory = gen_factory

    def run(self):
        ok = True
        try:
            for ev in self.gen_factory():
                self.event.emit(ev)
                if ev.get("step") == "error":
                    ok = False
        except Exception as e:
            self.event.emit({"step": "error", "msg": str(e)})
            ok = False
        self.finished.emit(ok)


class UpdateWorker(QObject):
    done = Signal(dict)

    def run(self):
        from app import updater
        try:
            self.done.emit(updater.check_and_update())
        except Exception as e:
            self.done.emit({"ok": False, "message": str(e)})


def run_in_thread(win, worker):
    """worker 를 QThread 에서 실행하고, 스레드 참조를 창에 보관(GC 방지)."""
    th = QThread()
    worker.moveToThread(th)
    th.started.connect(worker.run)
    win._threads.append((th, worker))
    th.start()
    return th


# ------------------------------------------------------------------ main window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Voice Studio")
        self.resize(1000, 760)
        ico = ROOT / "app" / "static" / "icon.ico"
        if ico.exists():
            self.setWindowIcon(QIcon(str(ico)))
        self._threads = []
        self.player = QMediaPlayer()
        self.audio_out = QAudioOutput()
        self.player.setAudioOutput(self.audio_out)
        self.last_file = None

        tabs = QTabWidget()
        tabs.addTab(self._tab_generate(), "음성 만들기")
        tabs.addTab(self._tab_train(), "목소리 학습")
        tabs.addTab(self._tab_library(), "보관함")
        tabs.addTab(self._tab_settings(), "설정")
        tabs.currentChanged.connect(self._on_tab)
        self.setCentralWidget(tabs)
        self.tabs = tabs
        self.refresh_voices()

    # ---------- 음성 만들기 ----------
    def _tab_generate(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(20, 20, 20, 20); v.setSpacing(12)
        v.addWidget(QLabel("<b>목소리</b>"))
        self.voice_combo = QComboBox()
        v.addWidget(self.voice_combo)
        v.addWidget(QLabel("<b>텍스트</b>"))
        self.text_edit = QTextEdit(); self.text_edit.setPlaceholderText("읽을 문장을 입력하세요. 장문도 자동으로 나눠 이어 붙입니다.")
        v.addWidget(self.text_edit, 1)

        # sliders
        form = QFormLayout()
        self.speed = self._slider(50, 150, 100)
        self.temperature = self._slider(50, 140, 100)
        self.topk = self._slider(1, 40, 15)
        self.reppen = self._slider(100, 200, 135)
        form.addRow("속도", self._sl_row(self.speed, lambda x: f"{x/100:.2f}×"))
        form.addRow("안정성", self._sl_row(self.temperature, lambda x: f"{x/100:.2f}"))
        form.addRow("억양 다양성", self._sl_row(self.topk, lambda x: str(x)))
        form.addRow("반복 억제", self._sl_row(self.reppen, lambda x: f"{x/100:.2f}"))
        box = QGroupBox("발음/톤 설정"); box.setLayout(form)
        v.addWidget(box)

        row = QHBoxLayout()
        self.gen_btn = QPushButton("생성하기"); self.gen_btn.clicked.connect(self.on_generate)
        self.gen_status = QLabel("")
        row.addWidget(self.gen_btn); row.addWidget(self.gen_status, 1)
        v.addLayout(row)
        self.gen_progress = QProgressBar(); self.gen_progress.setRange(0, 0); self.gen_progress.hide()
        v.addWidget(self.gen_progress)

        prow = QHBoxLayout()
        self.play_btn = QPushButton("▶ 재생"); self.play_btn.clicked.connect(self.on_play); self.play_btn.setEnabled(False)
        self.stop_btn = QPushButton("■ 정지"); self.stop_btn.clicked.connect(self.player.stop); self.stop_btn.setEnabled(False)
        self.save_btn = QPushButton("저장(다운로드)"); self.save_btn.clicked.connect(self.on_save); self.save_btn.setEnabled(False)
        prow.addWidget(self.play_btn); prow.addWidget(self.stop_btn); prow.addWidget(self.save_btn); prow.addStretch(1)
        v.addLayout(prow)
        return w

    def _slider(self, lo, hi, val):
        s = QSlider(Qt.Horizontal); s.setRange(lo, hi); s.setValue(val); return s

    def _sl_row(self, slider, fmt):
        w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(0, 0, 0, 0)
        lab = QLabel(fmt(slider.value())); lab.setMinimumWidth(48)
        slider.valueChanged.connect(lambda x: lab.setText(fmt(x)))
        h.addWidget(slider, 1); h.addWidget(lab); return w

    def on_generate(self):
        text = self.text_edit.toPlainText().strip()
        if not text:
            return QMessageBox.warning(self, "Voice Studio", "텍스트를 입력해 주세요.")
        vid = self.voice_combo.currentData()
        if not vid:
            return QMessageBox.warning(self, "Voice Studio", "먼저 목소리를 학습/선택해 주세요.")
        params = {"temperature": self.temperature.value() / 100, "top_k": self.topk.value(),
                  "top_p": 1.0, "repetition_penalty": self.reppen.value() / 100}
        self.gen_btn.setEnabled(False); self.gen_status.setText("생성 중… (최초 엔진 로딩은 시간이 걸려요)")
        self.gen_progress.show()
        wk = GenWorker(text, vid, self.speed.value() / 100, params)
        wk.done.connect(self._gen_done); wk.failed.connect(self._gen_failed)
        run_in_thread(self, wk)

    def _gen_done(self, path):
        self.last_file = path
        self.gen_btn.setEnabled(True); self.gen_progress.hide(); self.gen_status.setText("완료!")
        for b in (self.play_btn, self.stop_btn, self.save_btn):
            b.setEnabled(True)
        self.on_play()
        self.refresh_library()

    def _gen_failed(self, msg):
        self.gen_btn.setEnabled(True); self.gen_progress.hide(); self.gen_status.setText("")
        QMessageBox.critical(self, "생성 실패", msg)

    def on_play(self):
        if self.last_file:
            self.player.setSource(QUrl.fromLocalFile(self.last_file)); self.player.play()

    def on_save(self):
        if not self.last_file:
            return
        dst, _ = QFileDialog.getSaveFileName(self, "저장", str(Path.home() / "Downloads" / Path(self.last_file).name), "WAV (*.wav)")
        if dst:
            import shutil
            shutil.copy(self.last_file, dst)
            self.gen_status.setText("저장됨: " + dst)

    # ---------- 목소리 학습 ----------
    def _tab_train(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(20, 20, 20, 20); v.setSpacing(10)
        v.addWidget(QLabel("<b>목소리 이름</b>"))
        self.tr_name = QLineEdit(); self.tr_name.setPlaceholderText("예: 내레이터A"); v.addWidget(self.tr_name)
        v.addWidget(QLabel("<b>음성 소스</b>"))
        self.tr_source = QComboBox(); self.tr_source.addItems(["유튜브 주소", "파일 업로드"]); v.addWidget(self.tr_source)
        self.tr_url = QLineEdit(); self.tr_url.setPlaceholderText("https://www.youtube.com/watch?v=..."); v.addWidget(self.tr_url)
        frow = QHBoxLayout()
        self.tr_file = QLineEdit(); self.tr_file.setPlaceholderText("음성 파일 경로 (wav/mp3/m4a)")
        fbtn = QPushButton("파일 선택"); fbtn.clicked.connect(self._pick_file)
        frow.addWidget(self.tr_file, 1); frow.addWidget(fbtn); v.addLayout(frow)
        self.tr_clean = QCheckBox("이미 배경음이 없는 깨끗한 음성 (배경음 제거 건너뛰기)"); v.addWidget(self.tr_clean)
        self.tr_btn = QPushButton("학습 시작 (음성 추가)"); self.tr_btn.clicked.connect(self.on_train); v.addWidget(self.tr_btn)
        self.tr_log = QPlainTextEdit(); self.tr_log.setReadOnly(True); self.tr_log.setMaximumHeight(150); v.addWidget(self.tr_log)

        ft = QGroupBox("정밀 학습 (파인튜닝) — 재현도 향상")
        fv = QVBoxLayout(ft)
        fv.addWidget(QLabel("같은 목소리에 음성을 여러 번 추가한 뒤 파인튜닝하면 훨씬 또렷해집니다. (GPU, 수십 분)"))
        self.ft_combo = QComboBox(); fv.addWidget(self.ft_combo)
        self.ft_btn = QPushButton("파인튜닝 시작"); self.ft_btn.clicked.connect(self.on_finetune); fv.addWidget(self.ft_btn)
        self.ft_log = QPlainTextEdit(); self.ft_log.setReadOnly(True); self.ft_log.setMaximumHeight(150); fv.addWidget(self.ft_log)
        v.addWidget(ft)
        v.addStretch(1)
        return w

    def _pick_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "음성 파일", "", "오디오 (*.wav *.mp3 *.m4a *.flac)")
        if f:
            self.tr_file.setText(f); self.tr_source.setCurrentIndex(1)

    def on_train(self):
        name = self.tr_name.text().strip()
        if not name:
            return QMessageBox.warning(self, "Voice Studio", "목소리 이름을 입력해 주세요.")
        is_file = self.tr_source.currentIndex() == 1
        sep = not self.tr_clean.isChecked()
        self.tr_btn.setEnabled(False); self.tr_log.clear()

        def factory():
            from pipeline import train as t
            if is_file:
                if not self.tr_file.text().strip():
                    raise RuntimeError("파일을 선택해 주세요.")
                return t.run(name=name, engine="sovits", device="cuda", voices_dir=VOICES_DIR,
                             data_dir=DATA, source_file=self.tr_file.text().strip(), separate=sep)
            else:
                if not self.tr_url.text().strip():
                    raise RuntimeError("유튜브 주소를 입력해 주세요.")
                return t.run(name=name, url=self.tr_url.text().strip(), engine="sovits", device="cuda",
                             voices_dir=VOICES_DIR, data_dir=DATA, separate=sep)
        self._run_stream(factory, self.tr_log, self.tr_btn)

    def on_finetune(self):
        vid = self.ft_combo.currentData()
        if not vid:
            return QMessageBox.warning(self, "Voice Studio", "목소리를 선택해 주세요.")
        if QMessageBox.question(self, "파인튜닝", "GPU로 수십 분 걸릴 수 있어요. 시작할까요?") != QMessageBox.Yes:
            return
        self.ft_btn.setEnabled(False); self.ft_log.clear()

        def factory():
            from pipeline import engine_sovits
            ds = DATA / "datasets" / vid
            return engine_sovits.finetune(vid, vid, ds, VOICES_DIR / vid)
        self._run_stream(factory, self.ft_log, self.ft_btn)

    def _run_stream(self, factory, log_widget, btn):
        wk = StreamWorker(factory)
        wk.event.connect(lambda ev: self._on_stream_ev(ev, log_widget))
        wk.finished.connect(lambda ok: self._on_stream_done(ok, btn))
        run_in_thread(self, wk)

    def _on_stream_ev(self, ev, log_widget):
        if ev.get("msg"):
            log_widget.appendPlainText(ev["msg"])

    def _on_stream_done(self, ok, btn):
        btn.setEnabled(True)
        self.refresh_voices()
        if ok:
            btn_log = "완료"
        QMessageBox.information(self, "Voice Studio", "완료되었습니다." if ok else "오류가 발생했습니다. 로그를 확인하세요.")

    # ---------- 보관함 ----------
    def _tab_library(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(20, 20, 20, 20)
        v.addWidget(QLabel("<b>보관함</b> — 생성한 음성 목록"))
        self.lib_list = QListWidget(); v.addWidget(self.lib_list, 1)
        row = QHBoxLayout()
        for txt, fn in (("▶ 재생", self._lib_play), ("저장", self._lib_save), ("삭제", self._lib_delete), ("새로고침", self.refresh_library)):
            b = QPushButton(txt); b.clicked.connect(fn); row.addWidget(b)
        row.addStretch(1); v.addLayout(row)
        return w

    def _lib_sel(self):
        it = self.lib_list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _lib_play(self):
        f = self._lib_sel()
        if f: self.player.setSource(QUrl.fromLocalFile(str(OUTPUTS / f))); self.player.play()

    def _lib_save(self):
        f = self._lib_sel()
        if not f: return
        dst, _ = QFileDialog.getSaveFileName(self, "저장", str(Path.home() / "Downloads" / f), "WAV (*.wav)")
        if dst:
            import shutil; shutil.copy(OUTPUTS / f, dst)

    def _lib_delete(self):
        f = self._lib_sel()
        if not f: return
        if QMessageBox.question(self, "삭제", "이 음성을 삭제할까요?") == QMessageBox.Yes:
            (OUTPUTS / f).unlink(missing_ok=True); self.refresh_library()

    # ---------- 설정 ----------
    def _tab_settings(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(20, 20, 20, 20); v.setSpacing(12)
        self.sys_label = QLabel("장치 정보를 불러오는 중…"); v.addWidget(self.sys_label)
        self._load_sysinfo()
        urow = QHBoxLayout()
        upd = QPushButton("업데이트 확인 및 적용"); upd.clicked.connect(self.on_update)
        self.upd_status = QLabel("")
        urow.addWidget(upd); urow.addWidget(self.upd_status, 1); v.addLayout(urow)
        v.addWidget(QLabel("<b>로그</b>"))
        lrow = QHBoxLayout()
        self.log_src = QComboBox(); self.log_src.addItem("GPT-SoVITS 엔진", "sovits"); self.log_src.addItem("앱", "server")
        lref = QPushButton("새로고침"); lref.clicked.connect(self._load_logs)
        lrow.addWidget(self.log_src); lrow.addWidget(lref); lrow.addStretch(1); v.addLayout(lrow)
        self.log_box = QPlainTextEdit(); self.log_box.setReadOnly(True); v.addWidget(self.log_box, 1)
        return w

    def _load_sysinfo(self):
        try:
            import torch
            if torch.cuda.is_available():
                self.sys_label.setText(f"장치: {torch.cuda.get_device_name(0)} · CUDA {torch.version.cuda} · PyTorch {torch.__version__.split('+')[0]}")
            else:
                self.sys_label.setText("장치: CPU (GPU 미감지)")
        except Exception:
            self.sys_label.setText("장치: 정보 없음")

    def _load_logs(self):
        src = self.log_src.currentData()
        p = (ROOT / "engines" / "GPT-SoVITS" / "sovits_server.log") if src == "sovits" else (DATA / "server.log")
        if p.exists():
            txt = p.read_text(encoding="utf-8", errors="ignore")
            self.log_box.setPlainText("\n".join(txt.splitlines()[-400:]))
        else:
            self.log_box.setPlainText("(로그 없음)")

    def on_update(self):
        self.upd_status.setText("확인 중…")
        wk = UpdateWorker()
        wk.done.connect(self._update_done)
        run_in_thread(self, wk)

    def _update_done(self, r):
        self.upd_status.setText(r.get("message", ""))
        if r.get("updated"):
            self.upd_status.setText("업데이트 적용됨 — 잠시 후 자동으로 재시작합니다…")
            self._restart_app()

    def _restart_app(self):
        import subprocess
        pyw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
        if not pyw.exists():
            return
        ps = (
            "Start-Sleep -Seconds 2; "
            "Get-Process pythonw,python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue; "
            "Start-Sleep -Seconds 1; "
            f"Start-Process '{pyw}' -ArgumentList 'app_native.py' -WorkingDirectory '{ROOT}'"
        )
        subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                         creationflags=0x00000008)
        QApplication.quit()

    # ---------- shared ----------
    def _on_tab(self, i):
        if self.tabs.tabText(i) == "보관함":
            self.refresh_library()
        elif self.tabs.tabText(i) == "설정":
            self._load_logs()

    def refresh_voices(self):
        voices = list_voices()
        for combo in (self.voice_combo, self.ft_combo):
            cur = combo.currentData()
            combo.clear()
            for v in voices:
                label = v.get("name", v["id"])
                if v.get("mode") == "finetuned":
                    label += "  (학습됨)"
                combo.addItem(label, v["id"])
            idx = combo.findData(cur)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        self.refresh_library()

    def refresh_library(self):
        self.lib_list.clear()
        hist = OUTPUTS / "history.jsonl"
        seen = set()
        if hist.exists():
            for line in reversed(hist.read_text(encoding="utf-8").splitlines()):
                if not line.strip():
                    continue
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                f = e.get("file", "")
                if f in seen or not (OUTPUTS / f).exists():
                    continue
                seen.add(f)
                it = QListWidgetItem(f"{e.get('voice_name', '-')}  ·  {e.get('text', '')[:40]}  ·  {e.get('created', '')}")
                it.setData(Qt.UserRole, f)
                self.lib_list.addItem(it)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Voice Studio")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
