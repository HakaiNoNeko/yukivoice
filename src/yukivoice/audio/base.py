"""Backend interface: a virtual microphone plus per-app audio capture."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AppInfo:
    key: str      # stable id used to find the app's audio streams
    label: str    # what the user sees in the dropdown


@dataclass(frozen=True)
class Check:
    ok: bool
    text: str


class Backend:
    #: Name of the input device other apps should select as their microphone.
    mic_label = "YukiVoice Mic"
    #: True if capturing an app silences it on the speakers, so Monitor must
    #: loop it back; False if the app keeps playing normally (Windows).
    capture_mutes_app = True
    capturing: Optional[AppInfo] = None

    def prepare(self) -> Optional[str]:
        """Create the virtual mic. Returns an error message, or None when ready."""
        raise NotImplementedError

    def shutdown(self) -> None:
        raise NotImplementedError

    def mic_target(self):
        """miniaudio device that feeds the virtual mic (raises RuntimeError if missing)."""
        raise NotImplementedError

    def setup_checks(self) -> list:
        """List of Check results shown on the wizard's audio page."""
        raise NotImplementedError

    def list_apps(self) -> list:
        raise NotImplementedError

    def start_capture(self, app: AppInfo, monitor: bool) -> None:
        raise NotImplementedError

    def stop_capture(self) -> None:
        raise NotImplementedError

    def set_capture_monitor(self, on: bool) -> None:
        pass

    def poll(self) -> None:
        """Called about once a second while the app runs."""


class UnsupportedBackend(Backend):
    def prepare(self):
        return "This operating system isn't supported yet (Windows and Linux are)."

    def shutdown(self):
        pass

    def mic_target(self):
        raise RuntimeError(self.prepare())

    def setup_checks(self):
        return [Check(False, self.prepare())]

    def list_apps(self):
        return []

    def start_capture(self, app, monitor):
        raise RuntimeError(self.prepare())

    def stop_capture(self):
        pass
