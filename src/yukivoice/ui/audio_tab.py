"""Audio tab: play a file into the virtual mic, or capture another app's sound."""

import os
import shutil
import subprocess
import tempfile

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

from ..audio import player
from ..context import Context
from ..log import log

_FILTER = "Audio (*.wav *.mp3 *.flac *.ogg *.m4a *.aac *.opus *.wma *.mp4 *.mkv *.webm);;All files (*)"
_NATIVE = {".wav", ".mp3", ".flac", ".ogg"}  # decoded directly; the rest need ffmpeg


def _card(title):
    card = QFrame()
    card.setObjectName("card")
    lay = QVBoxLayout(card)
    t = QLabel(title)
    t.setObjectName("section")
    lay.addWidget(t)
    return card, lay


class AudioTab(QWidget):
    _file_done = Signal(int)

    def __init__(self, ctx: Context):
        super().__init__()
        self.ctx = ctx
        self.apps = []
        self.file = None
        self.playback = None
        self._tmp = None
        self._gen = 0  # ignores 'finished' signals from a clip we already replaced

        lay = QVBoxLayout(self)

        # ── file ──
        card, cl = _card("Play a file")
        row = QHBoxLayout()
        open_btn = QPushButton("Open…")
        open_btn.clicked.connect(self._open)
        row.addWidget(open_btn)
        self.file_label = QLabel("No file chosen")
        self.file_label.setObjectName("dim")
        row.addWidget(self.file_label, 1)
        self.play_btn = QPushButton("Play")
        self.play_btn.setObjectName("go")
        self.play_btn.setEnabled(False)
        self.play_btn.clicked.connect(self._toggle_play)
        row.addWidget(self.play_btn)
        cl.addLayout(row)
        lay.addWidget(card)
        self._file_done.connect(self._on_file_done)

        # ── capture ──
        card, cl = _card("Capture an app")
        row = QHBoxLayout()
        self.combo = QComboBox()
        row.addWidget(self.combo, 1)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        row.addWidget(refresh)
        self.cap_btn = QPushButton("Capture")
        self.cap_btn.setObjectName("go")
        self.cap_btn.clicked.connect(self._toggle_capture)
        row.addWidget(self.cap_btn)
        cl.addLayout(row)
        hint = ("The app has to be playing sound to show up. While captured, its audio goes to the mic "
                "(and your speakers when Monitor is on)." if ctx.backend.capture_mutes_app else
                "Pick the app whose sound you want to send. You keep hearing it as usual; "
                "it just also goes to the mic.")
        h = QLabel(hint)
        h.setObjectName("dim")
        h.setWordWrap(True)
        cl.addWidget(h)
        lay.addWidget(card)

        self.status = QLabel("")
        self.status.setObjectName("dim")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        lay.addStretch(1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)
        QTimer.singleShot(300, self.refresh)

    # ── file playback ───────────────────────────────────────────────────

    def _open(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose audio", os.path.expanduser("~"), _FILTER)
        if path:
            self.file = path
            self.file_label.setText(os.path.basename(path))
            self.play_btn.setEnabled(True)
            self._play()

    def _toggle_play(self):
        self._stop_play() if self.playback else self._play()

    def _decodable(self, path):
        if os.path.splitext(path)[1].lower() in _NATIVE:
            return path
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("This format needs ffmpeg installed. Use wav, mp3, flac or ogg instead.")
        self._cleanup_tmp()
        fd, self._tmp = tempfile.mkstemp(suffix=".wav", prefix="yukivoice-")
        os.close(fd)
        r = subprocess.run([ffmpeg, "-y", "-v", "error", "-i", path, "-vn", "-ac", "2", "-ar", "48000", self._tmp],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg couldn't read that file: {r.stderr.strip()[:200]}")
        return self._tmp

    def _cleanup_tmp(self):
        if self._tmp:
            try:
                os.unlink(self._tmp)
            except OSError:
                pass
            self._tmp = None

    def _play(self):
        if not self.file:
            return
        self._stop_play()
        try:
            path = self._decodable(self.file)
            self._gen += 1
            gen = self._gen
            self.playback = player.play_file(path, self.ctx.targets(), on_done=lambda: self._file_done.emit(gen))
        except Exception as e:
            log(f"play failed: {e}")
            self.status.setText(f"Couldn't play that: {e}")
            self.playback = None
            return
        self.play_btn.setText("Stop")
        self.play_btn.setObjectName("stop")
        self._restyle(self.play_btn)
        self.ctx.status.emit("busy", "playing")
        self.status.setText("")

    def _on_file_done(self, gen):
        if gen == self._gen:
            self._reset_play()

    def _stop_play(self):
        self._gen += 1
        pb, self.playback = self.playback, None
        if pb:
            pb.stop()
        self._reset_play()

    def _reset_play(self):
        self.playback = None
        self.play_btn.setText("Play")
        self.play_btn.setObjectName("go")
        self._restyle(self.play_btn)
        if not self.ctx.backend.capturing:
            self.ctx.status.emit("ready", "ready")

    @staticmethod
    def _restyle(w):
        w.style().unpolish(w)
        w.style().polish(w)

    # ── app capture ─────────────────────────────────────────────────────

    def refresh(self):
        try:
            self.apps = self.ctx.backend.list_apps()
        except Exception as e:
            self.status.setText(str(e))
            return
        self.combo.clear()
        for a in self.apps:
            self.combo.addItem(a.label, a.key)
        cap = self.ctx.backend.capturing
        if cap:
            self.combo.setCurrentIndex(max(self.combo.findData(cap.key), 0))
        elif not self.apps:
            self.status.setText("No app is playing sound right now — start something, then hit Refresh.")

    def _toggle_capture(self):
        if self.ctx.backend.capturing:
            self.ctx.backend.stop_capture()
            self._capture_ui(False)
            self.status.setText("Capture released.")
            self.refresh()
            return
        i = self.combo.currentIndex()
        if i < 0 or i >= len(self.apps):
            self.status.setText("Pick an app first (it has to be playing sound).")
            return
        try:
            self.ctx.backend.start_capture(self.apps[i], bool(self.ctx.settings["monitor"]))
        except Exception as e:
            log(f"capture failed: {e}")
            self.status.setText(f"Capture failed: {e}")
            return
        self._capture_ui(True)
        self.status.setText(f"{self.apps[i].label} → mic.")

    def _capture_ui(self, on):
        self.cap_btn.setText("Release" if on else "Capture")
        self.cap_btn.setObjectName("stop" if on else "go")
        self._restyle(self.cap_btn)
        cap = self.ctx.backend.capturing
        self.ctx.status.emit("busy" if on else "ready", f"capturing {cap.label}" if on and cap else "ready")

    def monitor_changed(self, on):
        try:
            self.ctx.backend.set_capture_monitor(on)
        except Exception as e:
            self.status.setText(f"Monitor failed: {e}")

    def _tick(self):
        self.ctx.backend.poll()
        was_on = self.cap_btn.text() == "Release"
        if was_on and not self.ctx.backend.capturing:
            self._capture_ui(False)
            self.status.setText("The captured app went away; capture released.")

    # ── lifecycle ───────────────────────────────────────────────────────

    def cleanup(self):
        self.timer.stop()
        self._stop_play()
        self._cleanup_tmp()
