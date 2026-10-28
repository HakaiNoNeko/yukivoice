"""Voice tab: type text → Kokoro → virtual mic."""

import html
import queue
import threading

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QSlider, QTextEdit, QVBoxLayout, QWidget)

from .. import tts
from ..audio import player
from ..context import Context
from ..log import log
from . import theme

_KIND_COLOR = {"sys": theme.DIM, "err": theme.ERR, "ok": theme.OK, "warn": theme.WARN}


class _Entry(QLineEdit):
    """Line edit where Up recalls what you said before."""

    def __init__(self, history):
        super().__init__()
        self._history = history
        self._pos = -1

    def keyPressEvent(self, e: QKeyEvent):
        if e.key() == Qt.Key.Key_Up and self._history:
            self._pos = min(self._pos + 1, len(self._history) - 1)
            self.setText(self._history[self._pos])
        elif e.key() == Qt.Key.Key_Down and self._pos >= 0:
            self._pos -= 1
            self.setText(self._history[self._pos] if self._pos >= 0 else "")
        else:
            if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._pos = -1
            super().keyPressEvent(e)


class _Worker(QThread):
    """Speaks queued messages one at a time."""
    state = Signal(str, str)   # (kind, text) for the indicator
    message = Signal(str, str)  # (kind, text) for the history

    def __init__(self, ctx: Context):
        super().__init__()
        self.ctx = ctx
        self.q = queue.Queue()
        self.current = None
        self._lock = threading.Lock()

    def run(self):
        while True:
            item = self.q.get()
            if item is None:      # shutdown sentinel
                return
            self._speak(*item)

    def _speak(self, text, voice, speed, language):
        self.state.emit("busy", "speaking")
        try:
            samples, sr = self.ctx.engine().synth(text, voice, speed, language)
            if not len(samples):
                return
            pb = player.play_samples(samples, sr, self.ctx.targets())
            with self._lock:
                self.current = pb
            pb.wait()
        except Exception as e:
            log(f"speak failed: {type(e).__name__}: {e}")
            self.message.emit("err", str(e))
        finally:
            with self._lock:
                self.current = None
            self.state.emit("ready" if self.q.empty() else "busy", "ready" if self.q.empty() else "speaking")

    def stop_all(self):
        while not self.q.empty():
            try:
                self.q.get_nowait()
            except queue.Empty:
                break
        with self._lock:
            if self.current:
                self.current.stop()


class VoiceTab(QWidget):
    def __init__(self, ctx: Context):
        super().__init__()
        self.ctx = ctx
        self._sent = []

        lay = QVBoxLayout(self)
        self.history = QTextEdit()
        self.history.setReadOnly(True)
        lay.addWidget(self.history, 1)

        opts = QHBoxLayout()
        opts.addWidget(QLabel("Voice"))
        self.voice = QComboBox()
        self.voice.setMinimumWidth(230)
        self.voice.currentIndexChanged.connect(self._voice_changed)
        opts.addWidget(self.voice, 1)
        opts.addWidget(QLabel("Language"))
        self.lang = QComboBox()
        self.lang.addItem("Auto", "auto")
        for code, label, _ in tts.LANGUAGES:
            self.lang.addItem(label, code)
        i = self.lang.findData(ctx.settings["language"])
        self.lang.setCurrentIndex(max(i, 0))
        self.lang.currentIndexChanged.connect(lambda _: ctx.settings.__setitem__("language", self.lang.currentData()))
        opts.addWidget(self.lang)
        opts.addWidget(QLabel("Speed"))
        self.speed = QSlider(Qt.Orientation.Horizontal)
        self.speed.setRange(50, 200)
        self.speed.setValue(int(ctx.settings["speed"] * 100))
        self.speed.setFixedWidth(110)
        self.speed_label = QLabel()
        self.speed_label.setMinimumWidth(34)
        self.speed.valueChanged.connect(self._speed_changed)
        self._speed_changed(self.speed.value(), save=False)
        opts.addWidget(self.speed)
        opts.addWidget(self.speed_label)
        lay.addLayout(opts)

        self.status = QLabel("")
        self.status.setObjectName("dim")
        lay.addWidget(self.status)

        row = QHBoxLayout()
        self.entry = _Entry(self._sent)
        self.entry.setPlaceholderText("Type here and press Enter…")
        self.entry.returnPressed.connect(self._send)
        row.addWidget(self.entry, 1)
        speak = QPushButton("Speak")
        speak.setObjectName("go")
        speak.clicked.connect(self._send)
        row.addWidget(speak)
        stop = QPushButton("Stop")
        stop.setToolTip("Stop speaking and clear the queue")
        stop.clicked.connect(self._stop)
        row.addWidget(stop)
        lay.addLayout(row)

        self.worker = _Worker(ctx)
        self.worker.state.connect(ctx.status.emit)
        self.worker.message.connect(self.log)
        self.worker.start()

        self.reload_voices()
        if not ctx.engine_ready():
            self.log("warn", "The voice engine isn't installed yet — open Tools → Setup wizard.")
        else:
            self.log("sys", f"Pick “{ctx.backend.mic_label}” as your microphone in Discord, games, etc.")
        self.entry.setFocus()

    # ── voices ──────────────────────────────────────────────────────────

    def reload_voices(self):
        want = self.ctx.settings["voice"]
        self.voice.blockSignals(True)
        self.voice.clear()
        try:
            ids = tts.voice_ids() if self.ctx.engine_ready() else []
        except Exception:
            ids = []
        if want not in ids:
            ids.append(want)
        for v in sorted((tts.describe_voice(i) for i in ids), key=lambda v: (v.lang_label, v.gender, v.name)):
            self.voice.addItem(f"{v.name} — {v.lang_label}, {v.gender}", v.id)
        self.voice.setCurrentIndex(max(self.voice.findData(want), 0))
        self.voice.blockSignals(False)

    def _voice_changed(self, _):
        if self.voice.currentData():
            self.ctx.settings["voice"] = self.voice.currentData()

    def _speed_changed(self, value, save=True):
        self.speed_label.setText(f"{value / 100:.2f}×")
        if save:
            self.ctx.settings["speed"] = value / 100

    # ── history / sending ───────────────────────────────────────────────

    def log(self, kind, text):
        color = _KIND_COLOR.get(kind, theme.TEXT)
        self.history.append(f'<span style="color:{color}">{html.escape(text)}</span>')

    def _send(self):
        text = self.entry.text().strip()
        if not text:
            return
        self.entry.clear()
        self._sent.insert(0, text)
        self.history.append(f'<span style="color:{theme.ACCENT}">you › </span>'
                            f'<b style="color:{theme.ACCENT_HI}">{html.escape(text)}</b>')
        self.worker.q.put((text, self.voice.currentData(), self.speed.value() / 100, self.lang.currentData()))
        n = self.worker.q.qsize()
        self.status.setText(f"{n} queued" if n > 1 else "")

    def _stop(self):
        self.worker.stop_all()
        self.status.setText("")

    def cleanup(self):
        self.worker.stop_all()
        self.worker.q.put(None)
        self.worker.wait(5000)

    def focus_entry(self):
        self.entry.setFocus()
        self.entry.selectAll()
