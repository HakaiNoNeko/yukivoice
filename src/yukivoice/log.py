"""Tiny file+stderr logger shared by every module."""

import datetime
import sys

from . import config

_MAX_BYTES = 512 * 1024


def log(msg: str) -> None:
    line = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    try:
        path = config.log_path()
        if path.exists() and path.stat().st_size > _MAX_BYTES:
            path.replace(path.with_suffix(".log.old"))
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    if sys.stderr:  # None in a windowed (no-console) Windows build
        print(line, file=sys.stderr, flush=True)
