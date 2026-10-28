"""Windows can't create a virtual microphone without a driver, so YukiVoice uses
VB-Audio's free "VB-Cable". The wizard downloads the official package from
vb-audio.com (we don't redistribute it) and launches its installer elevated.
"""

import io
import platform
import tempfile
import zipfile
from pathlib import Path

import requests

from ..log import log

URL = "https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack43.zip"
HOME_PAGE = "https://vb-audio.com/Cable/"
PLAYBACK_NAME = "CABLE Input"       # what YukiVoice plays into
RECORDING_NAME = "CABLE Output (VB-Audio Virtual Cable)"  # what other apps pick as mic


def download(progress=None) -> Path:
    """Fetch and unpack the driver pack; returns the folder."""
    buf = io.BytesIO()
    with requests.get(URL, stream=True, timeout=30) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length") or 0)
        for chunk in r.iter_content(1 << 16):
            buf.write(chunk)
            if progress and total:
                progress(buf.tell(), total)
    out = Path(tempfile.mkdtemp(prefix="yukivoice-vbcable-"))
    with zipfile.ZipFile(buf) as z:
        z.extractall(out)
    log(f"VB-Cable pack extracted to {out}")
    return out


def launch_installer(folder: Path) -> None:
    """Run VB-Cable's own installer with admin rights (it shows a UAC prompt and
    its own 'Install Driver' button)."""
    import ctypes
    name = "VBCABLE_Setup_x64.exe" if platform.machine().lower() in ("amd64", "x86_64", "arm64") \
        else "VBCABLE_Setup.exe"
    exe = next(folder.rglob(name), None)
    if not exe:
        raise RuntimeError(f"{name} not found in the downloaded package")
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", str(exe), None, str(exe.parent), 1)
    if rc <= 32:
        raise RuntimeError("The installer couldn't be started (was the admin prompt declined?)")
