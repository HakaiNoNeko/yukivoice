"""Shared state handed to the UI: settings, audio backend, TTS engine."""

from PySide6.QtCore import QObject, Signal

from . import tts
from .audio import Backend, get_backend
from .config import Settings


class Context(QObject):
    #: ("ready"|"busy"|"warn"|"off", text) — drives the indicator in the header
    status = Signal(str, str)
    #: emitted after setup changes the model or voice list
    engine_changed = Signal()

    def __init__(self):
        super().__init__()
        self.settings = Settings()
        self.backend: Backend = get_backend()
        self._engine = None

    def engine(self) -> tts.Engine:
        variant = self.settings["model"]
        if self._engine is None or self._engine.variant != variant:
            self._engine = tts.Engine(variant)
        return self._engine

    def engine_ready(self) -> bool:
        return tts.is_installed(self.settings["model"])

    def targets(self) -> list:
        """Playback targets: the virtual mic, plus the speakers when Monitor is on."""
        out = [self.backend.mic_target()]
        if self.settings["monitor"]:
            out.append(None)
        return out
