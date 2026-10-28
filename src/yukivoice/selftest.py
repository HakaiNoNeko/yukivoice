"""`yukivoice --selftest [--download standard] [--out report.json]`

Smoke test for packaged builds (used by CI): constructs the whole UI offscreen,
optionally downloads the model, and checks that speech is actually produced.
"""

import json
import os
import sys
import threading
import traceback


def run(argv) -> int:
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    variant = argv[argv.index("--download") + 1] if "--download" in argv else None
    report = {"ok": True, "steps": {}}

    def step(name, fn, required=True):
        try:
            report["steps"][name] = {"ok": True, "info": fn()}
        except Exception:
            report["steps"][name] = {"ok": False, "error": traceback.format_exc()}
            if required:
                report["ok"] = False

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    def ui():
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication

        from . import app as appmod
        from .context import Context
        from .ui import theme
        from .ui.main_window import MainWindow
        from .ui.wizard import SetupWizard
        qa = QApplication.instance() or QApplication(["selftest"])
        qa.setStyleSheet(theme.QSS)
        icon = QIcon(str(appmod.ASSETS / "icon.png"))
        if icon.isNull():
            raise RuntimeError("icon asset missing")
        ctx = Context()
        win = MainWindow(ctx, icon, lambda: None)
        SetupWizard(ctx, icon)
        win.cleanup()
        return f"backend={type(ctx.backend).__name__}"

    def download():
        from . import tts
        last = [0]

        def progress(done, total):
            pct = done * 100 // max(total, 1)
            if pct >= last[0] + 10:
                last[0] = pct
                print(f"  download {pct}%", file=sys.stderr, flush=True)
        tts.install(variant, progress, threading.Event())
        from .context import Context
        Context().settings["model"] = variant
        return f"installed {variant}"

    def speech():
        from . import tts
        from .context import Context
        ctx = Context()
        if not ctx.engine_ready():
            return "skipped (model not installed)"
        eng = ctx.engine()
        res = {}
        for name, text, voice in (("en", "Hello! This is a test.", "af_heart"),
                                  ("ja", "こんにちは、テストです。", "jf_alpha")):
            samples, sr = eng.synth(text, voice, 1.0, "auto")
            peak = float(abs(samples).max()) if len(samples) else 0.0
            if peak < 0.01:
                raise RuntimeError(f"{name}: synthesized audio is silent")
            res[name] = f"{len(samples) / sr:.1f}s peak={peak:.2f}"
        res["voices"] = len(ctx.voices())
        return res

    def updater_logic():
        from . import __version__, updater
        assert updater.parse_version("v0.10.0") > updater.parse_version("0.9.9")
        assert updater.is_newer("99.0.0") and not updater.is_newer(__version__)
        return f"version {__version__}"

    def devices():
        from .audio import player
        return [d["name"] for d in player.playback_devices()]

    def windows_extras():
        if sys.platform != "win32":
            return "n/a"
        import proctap  # noqa: F401
        import pycaw.pycaw  # noqa: F401
        from .audio import get_backend
        try:  # CI runners have no audio endpoint, so listing may legitimately fail
            return f"imports ok; {len(get_backend().list_apps())} audio sessions"
        except Exception as e:
            return f"imports ok; listing sessions failed (expected without audio hardware): {e}"

    step("ui", ui)
    if variant:
        step("download", download)
    step("speech", speech)
    step("updater", updater_logic)
    step("devices", devices, required=False)   # CI machines have no sound hardware
    step("windows_extras", windows_extras)

    text = json.dumps(report, indent=2, ensure_ascii=False)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
    if sys.stdout:
        print(text)
    return 0 if report["ok"] else 1
