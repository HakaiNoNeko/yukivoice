"""Application entry: single instance, first-run wizard, main window."""

import os
import signal
import sys
import traceback
from pathlib import Path

from . import APP_NAME, __version__
from .log import log

ASSETS = Path(__file__).parent / "assets"
SOCKET = "yukivoice-single-instance"


def _fix_input_method():
    # PySide's Qt has no fcitx plugin; on Wayland the native text-input protocol
    # does the job (fcitx5/ibus both speak it), so don't point Qt at a missing plugin.
    if sys.platform.startswith("linux") and os.environ.get("WAYLAND_DISPLAY"):
        if os.environ.get("QT_IM_MODULE", "").startswith("fcitx"):
            os.environ["QT_IM_MODULE"] = "wayland"


def _send_to_running(cmd: str) -> bool:
    from PySide6.QtNetwork import QLocalSocket
    s = QLocalSocket()
    s.connectToServer(SOCKET)
    if not s.waitForConnected(500):
        return False
    s.write(cmd.encode())
    s.waitForBytesWritten(500)
    s.disconnectFromServer()
    return True


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    args = set(argv[1:])
    if "--version" in args:
        print(f"{APP_NAME} {__version__}")
        return 0
    if "--selftest" in args:
        from .selftest import run
        return run(argv[1:])

    _fix_input_method()
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QIcon
    from PySide6.QtNetwork import QLocalServer
    from PySide6.QtWidgets import QApplication, QMessageBox

    from .context import Context
    from .ui import theme
    from .ui.main_window import MainWindow
    from .ui.wizard import SetupWizard

    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setDesktopFileName("yukivoice")
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(theme.QSS)
    icon = QIcon(str(ASSETS / "icon.png"))
    app.setWindowIcon(icon)

    # One instance owns the virtual mic. A second launch just wakes the first.
    cmd = "quick" if "--quick" in args else "show"
    if _send_to_running(cmd):
        return 0
    QLocalServer.removeServer(SOCKET)
    server = QLocalServer()
    server.listen(SOCKET)

    log("─" * 20 + f" {APP_NAME} {__version__} start " + "─" * 20)
    ctx = Context()
    win = None

    def run_wizard():
        w = SetupWizard(ctx, icon, win)
        if w.exec():
            if win:
                win.voice_tab.reload_voices()
                win.mic_ready(ctx.backend.prepare() if not ctx.backend.capturing else None)
        return w

    try:
        if "--setup" in args or not ctx.settings["setup_done"] or not ctx.engine_ready():
            run_wizard()

        err = ctx.backend.prepare()
        win = MainWindow(ctx, icon, run_wizard)
        win.mic_ready(err)
    except Exception:
        log("FATAL during startup:\n" + traceback.format_exc())
        QMessageBox.critical(None, APP_NAME, "YukiVoice couldn't start. Details are in the log:\n"
                             + str(ctx.settings.path.parent / "yukivoice.log"))
        return 1

    def on_connection():
        sock = server.nextPendingConnection()
        if sock.waitForReadyRead(300):
            msg = bytes(sock.readAll()).decode(errors="ignore")
            win.quick() if msg == "quick" else win.show_window()
        sock.disconnectFromServer()

    server.newConnection.connect(on_connection)
    app.aboutToQuit.connect(lambda: (win.cleanup(), ctx.backend.shutdown()))

    # Let Ctrl-C / SIGTERM quit cleanly (the virtual mic must be removed).
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: win.quit_app())
    beat = QTimer()
    beat.start(300)
    beat.timeout.connect(lambda: None)  # wakes the interpreter so signals get handled

    if "--minimized" not in args:
        win.show_window() if "--quick" not in args else win.quick()
    return app.exec()
