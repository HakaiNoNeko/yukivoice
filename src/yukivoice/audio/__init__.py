"""Platform audio backends. `get_backend()` returns the one for this OS."""

import sys

from .base import AppInfo, Backend, Check


def get_backend() -> Backend:
    if sys.platform == "win32":
        from .windows import WindowsBackend
        return WindowsBackend()
    if sys.platform.startswith("linux"):
        from .linux import LinuxBackend
        return LinuxBackend()
    from .base import UnsupportedBackend
    return UnsupportedBackend()


__all__ = ["AppInfo", "Backend", "Check", "get_backend"]
