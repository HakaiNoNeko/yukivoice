"""Self-update from GitHub releases.

A release tagged vX.Y.Z carries the builds (`YukiVoice.exe`, `YukiVoice-x86_64.AppImage`).
The app checks the latest release, and if it's newer, downloads the build for this
platform over the running one and restarts. Source runs and unpackaged installs only
get a notice with the release link.

While the repo is private, GitHub needs a token: `update_token` in settings.json, the
YUKIVOICE_GITHUB_TOKEN / GITHUB_TOKEN / GH_TOKEN env vars, or the `gh` CLI's login.
"""

import hashlib
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import requests

from . import __version__
from .log import log

REPO = "HakaiNoNeko/yukivoice"
_API = f"https://api.github.com/repos/{REPO}/releases/latest"
_ASSET = {"win32": "YukiVoice.exe", "linux": "YukiVoice-x86_64.AppImage"}


class UpdateError(Exception):
    pass


@dataclass
class Release:
    version: str
    url: str                 # release page
    notes: str
    asset_name: str = ""     # empty → no build for this platform
    asset_api_url: str = ""
    size: int = 0
    sha256: str = ""


def parse_version(tag: str) -> tuple:
    nums = re.findall(r"\d+", tag.split("-")[0])
    return tuple(int(n) for n in nums) or (0,)


def is_newer(tag: str, current: str = __version__) -> bool:
    return parse_version(tag) > parse_version(current)


def _token(settings) -> str:
    tok = (settings["update_token"] or "").strip()
    for var in ("YUKIVOICE_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        tok = tok or os.environ.get(var, "").strip()
    if not tok and shutil.which("gh"):
        try:
            tok = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True,
                                 timeout=5).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return tok


def _headers(token: str, accept: str = "application/vnd.github+json") -> dict:
    h = {"Accept": accept, "User-Agent": f"YukiVoice/{__version__}", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def latest(settings) -> Release:
    """The newest published release (newer or not). Raises UpdateError on failure."""
    token = _token(settings)
    try:
        r = requests.get(_API, headers=_headers(token), timeout=15)
    except requests.RequestException as e:
        raise UpdateError(f"Couldn't reach GitHub: {e}") from None
    if r.status_code == 404:
        raise UpdateError("GitHub says the release isn't there. The repository is private — set "
                          "`update_token` in settings.json (or sign in with the `gh` CLI).")
    if r.status_code in (401, 403):
        raise UpdateError(f"GitHub refused the request ({r.status_code}); check the update token.")
    r.raise_for_status()
    data = r.json()
    rel = Release(version=data["tag_name"].lstrip("v"), url=data["html_url"], notes=data.get("body") or "")
    want = _ASSET.get("win32" if sys.platform == "win32" else "linux")
    for a in data.get("assets", []):
        if a["name"] == want and a.get("state", "uploaded") == "uploaded":
            rel.asset_name, rel.asset_api_url, rel.size = a["name"], a["url"], a["size"]
            rel.sha256 = (a.get("digest") or "").removeprefix("sha256:")
    return rel


def check(settings):
    """The release to offer, or None when up to date / skipped."""
    rel = latest(settings)
    if not is_newer(rel.version):
        return None
    if rel.version == settings["skipped_version"]:
        return None
    return rel


# ── applying an update ──────────────────────────────────────────────────────

def install_target():
    """Path of the packaged build that's running, or None (source run, not updatable)."""
    if sys.platform == "win32":
        return Path(sys.executable) if getattr(sys, "frozen", False) else None
    app = os.environ.get("APPIMAGE")
    return Path(app) if app and Path(app).is_file() else None


def can_self_update() -> bool:
    return install_target() is not None


def download(rel: Release, settings, progress, dest: Path) -> None:
    """Fetch the release asset to `dest`, verifying size (and digest when GitHub gives one)."""
    if not rel.asset_api_url:
        raise UpdateError("This release has no build for your platform.")
    token = _token(settings)
    h = hashlib.sha256()
    got = 0
    with requests.get(rel.asset_api_url, headers=_headers(token, "application/octet-stream"),
                      stream=True, timeout=30) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 17):
                f.write(chunk)
                h.update(chunk)
                got += len(chunk)
                progress(got, rel.size)
    if rel.size and got != rel.size:
        raise UpdateError("The download was cut short; try again.")
    if rel.sha256 and h.hexdigest() != rel.sha256:
        raise UpdateError("The download is corrupt (checksum mismatch); try again.")


def apply(rel: Release, settings, progress) -> None:
    """Replace the running build with `rel`. The caller then calls `relaunch()` and quits."""
    target = install_target()
    if target is None:
        raise UpdateError("This copy of YukiVoice isn't a packaged build, so it can't update itself.")
    new = target.with_name(target.name + ".new")
    try:
        download(rel, settings, progress, new)
        if sys.platform == "win32":
            old = target.with_name(target.name + ".old")
            old.unlink(missing_ok=True)
            target.rename(old)          # a running exe can be renamed, not overwritten
            new.replace(target)
        else:
            new.chmod(target.stat().st_mode | 0o111)
            new.replace(target)         # the running AppImage keeps its old inode
    except requests.RequestException as e:
        raise UpdateError(f"Download failed: {e}") from None
    except OSError as e:
        raise UpdateError(f"Couldn't write {target} ({e}). Is the folder writable?") from None
    finally:
        new.unlink(missing_ok=True)
    log(f"updated {target} to {rel.version}")


def relaunch() -> None:
    """Start the new build once this process has quit (the single-instance lock is held until then)."""
    target = install_target()
    if target is None:
        return
    if sys.platform == "win32":
        subprocess.Popen(["cmd", "/c", "timeout", "/t", "2", "/nobreak", ">nul", "&", "start", "", str(target)],
                         creationflags=0x08000000, close_fds=True)   # CREATE_NO_WINDOW
    else:
        subprocess.Popen(["sh", "-c", 'sleep 2; exec "$0"', str(target)], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def cleanup_old() -> None:
    """Delete the previous exe left behind by a Windows update."""
    t = install_target()
    if t and sys.platform == "win32":
        t.with_name(t.name + ".old").unlink(missing_ok=True)
