"""Paths and persisted settings."""

import json
import os
import sys
from pathlib import Path


def _home_override():
    # Lets tests and portable setups keep everything in one folder.
    p = os.environ.get("YUKIVOICE_HOME")
    return Path(p) if p else None


def data_dir() -> Path:
    """Where downloaded models live."""
    override = _home_override()
    if override:
        base = override / "data"
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "YukiVoice"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "yukivoice"
    base.mkdir(parents=True, exist_ok=True)
    return base


def config_dir() -> Path:
    override = _home_override()
    if override:
        base = override / "config"
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "YukiVoice"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "yukivoice"
    base.mkdir(parents=True, exist_ok=True)
    return base


def model_dir() -> Path:
    d = data_dir() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_path() -> Path:
    return config_dir() / "yukivoice.log"


DEFAULTS = {
    "setup_done": False,
    "model": "standard",
    "voice": "af_heart",
    "speed": 1.0,
    "language": "auto",
    "monitor": True,
    "tray_hint_shown": False,
    # "local" = built-in Kokoro; "api" = an OpenAI-compatible speech server
    "engine": "local",
    "api_url": "http://127.0.0.1:18793/v1",
    "api_key": "",
    "api_model": "kokoro",
    # auto-update: checks GitHub releases; update_token is only needed while the repo is private
    "auto_update": True,
    "update_token": "",
    "skipped_version": "",
}


class Settings:
    def __init__(self):
        self.path = config_dir() / "settings.json"
        self.data = dict(DEFAULTS)
        try:
            self.data.update(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value
        self.save()

    def save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        tmp.replace(self.path)
