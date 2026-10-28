"""Windows backend: VB-Cable as the virtual mic + WASAPI process-loopback capture.

TTS and files are played into "CABLE Input"; other apps record "CABLE Output".
App capture taps one process's audio (Windows 10 2004+ / Windows 11) and plays it
into the cable too. The app keeps playing on the speakers as usual.
"""

import os
from typing import Optional

from ..log import log
from . import player, vbcable
from .base import AppInfo, Backend, Check


class WindowsBackend(Backend):
    mic_label = vbcable.RECORDING_NAME
    capture_mutes_app = False

    def __init__(self):
        self._tap = None
        self._pipe = None
        self._play = None
        self.capturing = None

    def cable_device(self):
        return player.find_playback(vbcable.PLAYBACK_NAME)

    def prepare(self):
        if not self.cable_device():
            return ("VB-Cable isn't installed, so there's no virtual mic yet. "
                    "Run Tools → Setup wizard to install it.")
        return None

    def shutdown(self):
        if self.capturing:
            self.stop_capture()

    def mic_target(self):
        dev = self.cable_device()
        if not dev:
            raise RuntimeError("VB-Cable isn't installed (Tools → Setup wizard).")
        return dev

    def setup_checks(self):
        ok = self.cable_device() is not None
        return [Check(ok, "VB-Cable virtual microphone found" if ok else
                      "VB-Cable (the virtual microphone driver) is not installed yet")]

    # ── app capture ─────────────────────────────────────────────────────

    def list_apps(self):
        try:
            from pycaw.pycaw import AudioUtilities
            sessions = AudioUtilities.GetAllSessions()
        except Exception as e:
            log(f"listing audio sessions failed: {e}")
            raise RuntimeError(f"Couldn't list apps: {e}")
        me = os.getpid()
        found = {}
        for s in sessions:
            pid = getattr(s, "ProcessId", 0)
            if not pid or pid == me:
                continue
            try:
                name = s.Process.name() if s.Process else f"pid {pid}"
            except Exception:
                name = f"pid {pid}"
            found[str(pid)] = name
        names = list(found.values())
        return sorted((AppInfo(pid, name if names.count(name) == 1 else f"{name} (pid {pid})")
                       for pid, name in found.items()), key=lambda a: a.label.lower())

    def start_capture(self, app, monitor):
        try:
            from proctap import ProcessAudioCapture
        except ImportError as e:
            raise RuntimeError(f"App capture isn't available in this build: {e}")
        dev = self.mic_target()
        self._pipe = player.PcmPipe()
        self._play = player.play_pipe(self._pipe, [dev])
        try:
            self._tap = ProcessAudioCapture(int(app.key), on_data=lambda pcm, frames: self._pipe.feed(pcm))
            self._tap.start()
        except Exception as e:
            self.stop_capture()
            raise RuntimeError(f"Couldn't capture {app.label}: {e}")
        self.capturing = app

    def stop_capture(self):
        tap, self._tap = self._tap, None
        if tap:
            try:
                tap.stop()
            except Exception as e:
                log(f"stopping capture: {e}")
        if self._pipe:
            self._pipe.closed = True
        play, self._play = self._play, None
        if play:
            play.stop()
        self._pipe = None
        self.capturing = None

    def poll(self):
        # The captured app closed → drop the capture quietly.
        if self.capturing and self._tap and not self._tap.is_running:
            log(f"capture of {self.capturing.label} ended")
            self.stop_capture()
