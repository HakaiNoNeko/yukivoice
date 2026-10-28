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

    def _variant(self) -> str:
        v = self.settings["model"]
        return v if v in tts.MODELS else "standard"   # e.g. a setting left by an older build

    def uses_api(self) -> bool:
        return self.settings["engine"] == "api"

    def engine(self):
        variant = "api" if self.uses_api() else self._variant()
        if self._engine is None or self._engine.variant != variant:
            self._engine = tts.RemoteEngine(self.settings) if self.uses_api() else tts.Engine(variant)
        return self._engine

    def engine_ready(self) -> bool:
        return True if self.uses_api() else tts.is_installed(self._variant())

    def voices(self) -> list:
        """Voices the current engine can speak. Raises if the custom API can't be reached."""
        if self.uses_api():
            return [tts.describe_voice(v) for v in self.engine().list_voices()]
        return tts.all_voices(self.engine_ready())

    def targets(self) -> list:
        """Playback targets: the virtual mic, plus the speakers when Monitor is on."""
        out = [self.backend.mic_target()]
        if self.settings["monitor"]:
            out.append(None)
        return out
