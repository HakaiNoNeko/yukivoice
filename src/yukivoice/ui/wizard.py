"""First-run setup wizard: audio driver → Kokoro install → voice choice."""

import sys
import threading

from PySide6.QtCore import QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QProgressBar, QPushButton, QRadioButton,
                               QVBoxLayout, QWidget, QWizard, QWizardPage)

from .. import APP_NAME, tts
from ..audio import player
from ..context import Context
from ..log import log


def _label(text, name=None, wrap=True):
    lab = QLabel(text)
    lab.setWordWrap(wrap)
    if name:
        lab.setObjectName(name)
    return lab


# ── workers ─────────────────────────────────────────────────────────────────

class _InstallWorker(QThread):
    progress = Signal(int, int)
    failed = Signal(str)
    finished_ok = Signal()

    def __init__(self, variant):
        super().__init__()
        self.variant = variant
        self.cancel = threading.Event()

    def run(self):
        try:
            tts.install(self.variant, lambda d, t: self.progress.emit(d, t), self.cancel)
            self.finished_ok.emit()
        except tts.Cancelled:
            self.failed.emit("Cancelled — click Install to resume.")
        except Exception as e:
            log(f"install failed: {e}")
            self.failed.emit(f"Download failed: {e}")


class _ApiTestWorker(QThread):
    result = Signal(str)

    def __init__(self, engine):
        super().__init__()
        self.engine = engine

    def run(self):
        try:
            n = len(self.engine.list_voices())
            self.result.emit(f"✅ Connected — the server offers {n} voices.")
        except Exception as e:
            self.result.emit(f"⚠️ {type(e).__name__}: {e}")


class _CableWorker(QThread):
    progress = Signal(int, int)
    failed = Signal(str)
    launched = Signal()

    def run(self):
        try:
            from ..audio import vbcable
            folder = vbcable.download(lambda d, t: self.progress.emit(d, t))
            vbcable.launch_installer(folder)
            self.launched.emit()
        except Exception as e:
            log(f"VB-Cable install failed: {e}")
            self.failed.emit(str(e))


class _PreviewWorker(QThread):
    failed = Signal(str)

    def __init__(self, engine, voice):
        super().__init__()
        self.engine, self.voice = engine, voice

    def run(self):
        try:
            v = tts.describe_voice(self.voice)
            samples, sr = self.engine.synth(tts.sample_text(v.lang), self.voice, 1.0, v.lang)
            player.play_samples(samples, sr, [None]).wait()  # your normal speakers
        except Exception as e:
            self.failed.emit(str(e))


# ── pages ───────────────────────────────────────────────────────────────────

class _Welcome(QWizardPage):
    def __init__(self, ctx):
        super().__init__()
        self.setTitle(f"Welcome to {APP_NAME}")
        lay = QVBoxLayout(self)
        lay.addWidget(_label(
            f"{APP_NAME} turns text and app audio into a virtual microphone. Type something and it's "
            "spoken in your chosen voice in Discord, games, calls — anywhere that takes a microphone. "
            "You can also play sound files or send another app's audio to the mic."))
        lay.addWidget(_label("This wizard will:"))
        lay.addWidget(_label("  1.  Check your audio setup (and install the virtual mic driver on Windows)\n"
                             "  2.  Set up the voice engine (built-in Kokoro download, or your own custom API)\n"
                             "  3.  Let you pick the voice you want to use"))
        lay.addStretch(1)


class _AudioPage(QWizardPage):
    def __init__(self, ctx: Context):
        super().__init__()
        self.ctx = ctx
        self._worker = None
        self._win = sys.platform == "win32"
        self.setTitle("Audio setup")
        self.setSubTitle("The virtual microphone is what other apps will hear.")
        lay = QVBoxLayout(self)
        self.checks = _label("")
        lay.addWidget(self.checks)
        if self._win:
            lay.addWidget(_label(
                "Windows needs a small driver to make a virtual microphone. YukiVoice uses the free "
                "<b>VB-Cable</b> by VB-Audio. Click the button to download it from vb-audio.com and start "
                "its installer. Approve the admin prompt, then click <b>Install Driver</b> in its window.",
            ))
            row = QHBoxLayout()
            self.install_btn = QPushButton("Download and install VB-Cable")
            self.install_btn.setObjectName("go")
            self.install_btn.clicked.connect(self._install)
            row.addWidget(self.install_btn)
            web = QPushButton("vb-audio.com")
            web.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://vb-audio.com/Cable/")))
            row.addWidget(web)
            row.addStretch(1)
            lay.addLayout(row)
            self.bar = QProgressBar()
            self.bar.hide()
            lay.addWidget(self.bar)
        else:
            lay.addWidget(_label(f"YukiVoice creates its own microphone, <b>{ctx.backend.mic_label}</b>, when it "
                                 "starts and removes it when you quit. Nothing needs to be installed."))
        self.note = _label("", "dim")
        lay.addWidget(self.note)
        lay.addStretch(1)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._recheck)

    def initializePage(self):
        self._recheck()
        if self._win:
            self.timer.start(2000)

    def cleanupPage(self):
        self.timer.stop()

    def _recheck(self):
        results = self.ctx.backend.setup_checks()
        self.checks.setText("<br>".join(f"{'✅' if c.ok else '⚠️'}  {c.text}" for c in results))
        ok = all(c.ok for c in results)
        if self._win:
            self.install_btn.setEnabled(not ok and not (self._worker and self._worker.isRunning()))
            if ok:
                self.note.setText(f"Great — in Discord and other apps, choose <b>{self.ctx.backend.mic_label}</b> "
                                  "as your microphone.")
        elif not ok:
            self.note.setText("Fix the item above, then reopen the wizard from Tools → Setup wizard.")

    def _install(self):
        self.install_btn.setEnabled(False)
        self.bar.show()
        self.note.setText("Downloading VB-Cable…")
        w = self._worker = _CableWorker()
        w.progress.connect(lambda d, t: (self.bar.setMaximum(t), self.bar.setValue(d)))
        w.failed.connect(self._failed)
        w.launched.connect(lambda: (self.bar.hide(), self.note.setText(
            "The VB-Cable installer is open. Click <b>Install Driver</b>, wait for it to finish, then come back "
            "here — this page updates by itself. (If it doesn't, restart your PC and reopen this wizard.)")))
        w.start()

    def _failed(self, msg):
        self.bar.hide()
        self.install_btn.setEnabled(True)
        self.note.setText(f"⚠️ {msg} — you can also install it by hand from vb-audio.com/Cable.")


class _EnginePage(QWizardPage):
    def __init__(self, ctx: Context):
        super().__init__()
        self.ctx = ctx
        self._worker = None
        self._test = None
        self.setTitle("Voice engine")
        self.setSubTitle("Choose where speech comes from.")
        lay = QVBoxLayout(self)
        self.mode_local = QRadioButton("Built-in Kokoro (offline, one-time download)")
        self.mode_api = QRadioButton("Custom API (an OpenAI-compatible speech server you run)")
        (self.mode_api if ctx.uses_api() else self.mode_local).setChecked(True)
        lay.addWidget(self.mode_local)

        # ── built-in ──
        self.local_box = QWidget()
        ll = QVBoxLayout(self.local_box)
        ll.setContentsMargins(24, 0, 0, 0)
        ll.addWidget(_label("Kokoro runs on your computer — no account, nothing is sent anywhere. "
                            "The model (about 350 MB with the voice pack) is a one-time download."))
        self.group = QButtonGroup(self)
        self.radios = {}
        for key, (text, _) in tts.MODELS.items():
            r = QRadioButton(text)
            self.group.addButton(r)
            self.radios[key] = r
            ll.addWidget(r)
        self.radios[ctx.settings["model"] if ctx.settings["model"] in tts.MODELS else "standard"].setChecked(True)
        for r in self.radios.values():
            r.toggled.connect(self._refresh)
            r.setVisible(len(self.radios) > 1)   # nothing to choose while there's one model
        row = QHBoxLayout()
        self.btn = QPushButton("Download and install Kokoro")
        self.btn.setObjectName("go")
        self.btn.clicked.connect(self._toggle)
        row.addWidget(self.btn)
        row.addStretch(1)
        ll.addLayout(row)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        ll.addWidget(self.bar)
        self.msg = _label("", "dim")
        ll.addWidget(self.msg)
        lay.addWidget(self.local_box)

        lay.addWidget(self.mode_api)
        # ── custom API ──
        self.api_box = QWidget()
        al = QVBoxLayout(self.api_box)
        al.setContentsMargins(24, 0, 0, 0)
        al.addWidget(_label("Text is sent to the server and the audio that comes back goes to the virtual mic. "
                            "The server must offer <b>POST {address}/audio/speech</b> and <b>GET {address}/voices</b>."))
        self.api_url = QLineEdit(ctx.settings["api_url"])
        self.api_url.setPlaceholderText("http://127.0.0.1:18793/v1")
        self.api_key = QLineEdit(ctx.settings["api_key"])
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("API key (leave empty if the server needs none)")
        self.api_model = QLineEdit(ctx.settings["api_model"])
        for label, edit in (("Address", self.api_url), ("Key", self.api_key), ("Model", self.api_model)):
            r = QHBoxLayout()
            lab = QLabel(label)
            lab.setMinimumWidth(52)
            r.addWidget(lab)
            r.addWidget(edit, 1)
            al.addLayout(r)
            edit.textChanged.connect(lambda *_: self.completeChanged.emit())
        row = QHBoxLayout()
        self.test_btn = QPushButton("Test connection")
        self.test_btn.clicked.connect(self._test_api)
        row.addWidget(self.test_btn)
        self.api_msg = _label("", "dim")
        row.addWidget(self.api_msg, 1)
        al.addLayout(row)
        lay.addWidget(self.api_box)
        lay.addStretch(1)

        for r in (self.mode_local, self.mode_api):
            r.toggled.connect(self._mode_changed)
        self._mode_changed()

    def api(self) -> bool:
        return self.mode_api.isChecked()

    def _mode_changed(self, *_):
        self.local_box.setVisible(not self.api())
        self.api_box.setVisible(self.api())
        self._refresh()
        self.completeChanged.emit()

    def variant(self):
        return next(k for k, r in self.radios.items() if r.isChecked())

    def initializePage(self):
        self._refresh()

    def _refresh(self, *_):
        if self._worker and self._worker.isRunning():
            return
        have = tts.is_installed(self.variant())
        self.bar.setValue(1000 if have else 0)
        self.btn.setText("Installed ✓" if have else "Download and install Kokoro")
        self.btn.setEnabled(not have)
        self.msg.setText("Already installed — click Next." if have else "")
        self.completeChanged.emit()

    def isComplete(self):
        if self.api():
            return bool(self.api_url.text().strip())
        return tts.is_installed(self.variant()) and not (self._worker and self._worker.isRunning())

    # ── custom API ──
    def _test_api(self):
        probe = dict(api_url=self.api_url.text(), api_key=self.api_key.text(), api_model=self.api_model.text())
        self.test_btn.setEnabled(False)
        self.api_msg.setText("Connecting…")
        w = self._test = _ApiTestWorker(tts.RemoteEngine(probe))
        w.result.connect(self.api_msg.setText)
        w.finished.connect(lambda: self.test_btn.setEnabled(True))
        w.start()

    # ── built-in ──
    def _toggle(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel.set()
            return
        for r in self.radios.values():
            r.setEnabled(False)
        w = self._worker = _InstallWorker(self.variant())
        w.progress.connect(self._progress)
        w.failed.connect(self._failed)
        w.finished_ok.connect(self._done)
        self.btn.setText("Cancel")
        self.msg.setText("Downloading…")
        w.start()

    def _progress(self, done, total):
        self.bar.setValue(int(done * 1000 / max(total, 1)))
        self.msg.setText(f"Downloading… {done / 1e6:.0f} / {total / 1e6:.0f} MB")

    def _failed(self, msg):
        self._worker.wait()
        for r in self.radios.values():
            r.setEnabled(True)
        self.btn.setText("Retry")
        self.msg.setText(msg)
        self.completeChanged.emit()

    def _done(self):
        self._worker.wait()
        for r in self.radios.values():
            r.setEnabled(True)
        self.ctx.settings["model"] = self.variant()
        self._refresh()

    def validatePage(self):
        s = self.ctx.settings
        if self.api():
            s["engine"] = "api"
            s["api_url"] = self.api_url.text().strip().rstrip("/")
            s["api_key"] = self.api_key.text().strip()
            s["api_model"] = self.api_model.text().strip() or "kokoro"
        else:
            s["engine"] = "local"
            s["model"] = self.variant()
        return True


class _VoicePage(QWizardPage):
    def __init__(self, ctx: Context):
        super().__init__()
        self.ctx = ctx
        self._preview = None
        self.setTitle("Choose your voice")
        self.setSubTitle("Pick a language, then a voice. Preview plays through your speakers, not the mic.")
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("Language"))
        self.lang = QComboBox()
        self.lang.currentIndexChanged.connect(self._fill)
        row.addWidget(self.lang, 1)
        lay.addLayout(row)
        self.list = QListWidget()
        self.list.currentItemChanged.connect(lambda *_: self.completeChanged.emit())
        self.list.itemDoubleClicked.connect(lambda *_: self._play())
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.prev = QPushButton("▶  Preview")
        self.prev.clicked.connect(self._play)
        row.addWidget(self.prev)
        self.msg = _label("", "dim")
        row.addWidget(self.msg, 1)
        lay.addLayout(row)
        self._voices = []

    def initializePage(self):
        try:
            self._voices = self.ctx.voices()
        except Exception as e:
            self._voices = []
            self.msg.setText(f"Couldn't load the voice list: {e}")
        current = tts.describe_voice(self.ctx.settings["voice"])
        self.lang.blockSignals(True)
        self.lang.clear()
        for code, label, _ in tts.LANGUAGES:
            if any(v.lang == code for v in self._voices):
                self.lang.addItem(label, code)
        self.lang.setCurrentIndex(max(self.lang.findData(current.lang), 0))
        self.lang.blockSignals(False)
        self._fill()
        for i in range(self.list.count()):
            if self.list.item(i).data(0x100) == current.id:
                self.list.setCurrentRow(i)

    def _fill(self, *_):
        self.list.clear()
        for v in sorted((v for v in self._voices if v.lang == self.lang.currentData()),
                        key=lambda v: (v.gender, v.name)):
            item = QListWidgetItem(v.display)
            item.setData(0x100, v.id)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def selected(self):
        item = self.list.currentItem()
        return item.data(0x100) if item else None

    def isComplete(self):
        return self.selected() is not None

    def _play(self):
        voice = self.selected()
        if not voice or (self._preview and self._preview.isRunning()):
            return
        self.msg.setText("Generating…")
        self.prev.setEnabled(False)
        w = self._preview = _PreviewWorker(self.ctx.engine(), voice)
        w.failed.connect(lambda m: self.msg.setText(f"Preview failed: {m}"))
        w.finished.connect(lambda: (self.prev.setEnabled(True),
                                    self.msg.setText("") if self.msg.text() == "Generating…" else None))
        w.start()

    def validatePage(self):
        self.ctx.settings["voice"] = self.selected()
        return True


class _Finish(QWizardPage):
    def __init__(self, ctx: Context):
        super().__init__()
        self.ctx = ctx
        self.setTitle("All set!")
        lay = QVBoxLayout(self)
        self.text = _label("")
        lay.addWidget(self.text)
        lay.addStretch(1)

    def initializePage(self):
        v = tts.describe_voice(self.ctx.settings["voice"])
        self.text.setText(
            f"Voice: <b>{v.name}</b> ({v.lang_label}, {v.gender}) — you can change it any time on the Voice tab.<br><br>"
            f"In Discord, your game, OBS or any call, choose <b>{self.ctx.backend.mic_label}</b> as the "
            "microphone. Then type a message in YukiVoice and press Enter.<br><br>"
            "Closing the window keeps YukiVoice running in the tray so the mic stays live. "
            "Quit from the tray menu. You can rerun this wizard from Tools → Setup wizard.")


class SetupWizard(QWizard):
    def __init__(self, ctx: Context, icon: QIcon, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle(f"{APP_NAME} setup")
        self.setWindowIcon(icon)
        self.setWizardStyle(QWizard.WizardStyle.ClassicStyle)
        self.setPixmap(QWizard.WizardPixmap.LogoPixmap, icon.pixmap(48, 48))
        self.setOption(QWizard.WizardOption.NoCancelButtonOnLastPage, True)
        self.resize(640, 480)
        for page in (_Welcome(ctx), _AudioPage(ctx), _EnginePage(ctx), _VoicePage(ctx), _Finish(ctx)):
            self.addPage(page)

    def done(self, result):
        # Don't leave downloads or previews running when the wizard closes.
        for page_id in self.pageIds():
            page = self.page(page_id)
            for attr in ("_worker", "_preview"):
                w = getattr(page, attr, None)
                if w and w.isRunning():
                    getattr(w, "cancel", threading.Event()).set()
                    w.wait(15000)
        if result == QWizard.DialogCode.Accepted:
            self.ctx.settings["setup_done"] = True
            self.ctx.engine_changed.emit()
        super().done(result)
