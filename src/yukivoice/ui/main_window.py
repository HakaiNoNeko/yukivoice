"""Main window: Voice and Audio tabs, a Monitor toggle, and a tray icon."""

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QDesktopServices, QIcon
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QApplication, QCheckBox, QHBoxLayout, QLabel, QMainWindow, QMenu,
                               QMessageBox, QProgressDialog, QSystemTrayIcon, QTabWidget, QVBoxLayout,
                               QWidget)

from .. import APP_NAME, __version__, config, updater
from ..context import Context
from ..log import log
from . import theme
from .audio_tab import AudioTab
from .custom_voices import CustomVoicesDialog
from .voice_tab import VoiceTab

_DOT = {"ready": theme.OK, "busy": theme.ACCENT, "warn": theme.WARN, "off": theme.DIM}


class _UpdateWorker(QThread):
    """Checks for a release (mode "check"), or downloads and installs one (mode "apply")."""
    found = Signal(object)      # Release | None
    failed = Signal(str)
    progress = Signal(int, int)
    installed = Signal()

    def __init__(self, settings, rel=None):
        super().__init__()
        self.settings, self.rel = settings, rel

    def run(self):
        try:
            if self.rel is None:
                self.found.emit(updater.check(self.settings))
            else:
                updater.apply(self.rel, self.settings, lambda d, t: self.progress.emit(d, t))
                self.installed.emit()
        except updater.UpdateError as e:
            self.failed.emit(str(e))
        except Exception as e:
            log(f"update failed: {type(e).__name__}: {e}")
            self.failed.emit(f"{type(e).__name__}: {e}")


class MainWindow(QMainWindow):
    def __init__(self, ctx: Context, icon: QIcon, run_wizard):
        super().__init__()
        self.ctx = ctx
        self._run_wizard = run_wizard
        self._quitting = False
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icon)
        self.resize(660, 520)

        central = QWidget()
        self.setCentralWidget(central)
        lay = QVBoxLayout(central)

        head = QHBoxLayout()
        title = QLabel(APP_NAME)
        title.setObjectName("title")
        head.addWidget(title)
        head.addStretch(1)
        self.monitor = QCheckBox("Monitor")
        self.monitor.setToolTip("Also play through your speakers so you can hear what you send")
        self.monitor.setChecked(bool(ctx.settings["monitor"]))
        self.monitor.toggled.connect(self._monitor_toggled)
        head.addWidget(self.monitor)
        self.dot = QLabel("● starting")
        head.addWidget(self.dot)
        lay.addLayout(head)

        self.tabs = QTabWidget()
        self.voice_tab = VoiceTab(ctx)
        self.audio_tab = AudioTab(ctx)
        self.tabs.addTab(self.voice_tab, "Voice")
        self.tabs.addTab(self.audio_tab, "Audio")
        lay.addWidget(self.tabs, 1)

        ctx.status.connect(self._set_status)
        ctx.engine_changed.connect(self.voice_tab.reload_voices)
        self._build_menu()
        self.tray = self._build_tray(icon)
        self._update_worker = None
        updater.cleanup_old()
        if ctx.settings["auto_update"]:
            QTimer.singleShot(4000, lambda: self.check_updates(silent=True))

    # ── status ──────────────────────────────────────────────────────────

    def _set_status(self, kind, text):
        self.dot.setText(f"● {text}")
        self.dot.setStyleSheet(f"color: {_DOT.get(kind, theme.DIM)};")

    def mic_ready(self, err):
        if err:
            self._set_status("warn", "no mic")
            self.voice_tab.log("warn", err)
        else:
            self._set_status("ready", "ready")

    def _monitor_toggled(self, on):
        self.ctx.settings["monitor"] = on
        self.audio_tab.monitor_changed(on)

    # ── menu / tray ─────────────────────────────────────────────────────

    def _build_menu(self):
        tools = self.menuBar().addMenu("Tools")
        act = QAction("Setup wizard…", self)
        act.triggered.connect(self._run_wizard)
        tools.addAction(act)
        act = QAction("Custom voices…", self)
        act.triggered.connect(lambda: CustomVoicesDialog(self.ctx, self).exec())
        tools.addAction(act)
        act = QAction("Check for updates…", self)
        act.triggered.connect(lambda: self.check_updates(silent=False))
        tools.addAction(act)
        act = QAction("Check for updates on startup", self)
        act.setCheckable(True)
        act.setChecked(bool(self.ctx.settings["auto_update"]))
        act.toggled.connect(lambda on: self.ctx.settings.__setitem__("auto_update", on))
        tools.addAction(act)
        act = QAction("Open log folder", self)
        act.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(config.config_dir()))))
        tools.addAction(act)
        tools.addSeparator()
        act = QAction("Quit", self)
        act.triggered.connect(self.quit_app)
        tools.addAction(act)
        helpm = self.menuBar().addMenu("Help")
        act = QAction("About", self)
        act.triggered.connect(lambda: QMessageBox.about(
            self, f"About {APP_NAME}",
            f"<b>{APP_NAME}</b> {__version__}<br>Text-to-speech and app audio, sent to a virtual microphone.<br><br>"
            f"Speech by Kokoro. Pick <b>{self.ctx.backend.mic_label}</b> as your microphone."))
        helpm.addAction(act)

    def _build_tray(self, icon):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return None
        tray = QSystemTrayIcon(icon, self)
        tray.setToolTip(APP_NAME)
        menu = QMenu()
        menu.addAction("Show YukiVoice", self.show_window)
        menu.addAction("Quick speak", self.quick)
        menu.addSeparator()
        menu.addAction("Quit", self.quit_app)
        tray.setContextMenu(menu)
        tray.activated.connect(lambda r: self._tray_click(r))
        tray.show()
        self._tray_menu = menu
        return tray

    def _tray_click(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.hide() if self.isVisible() else self.show_window()

    def show_window(self):
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()

    def quick(self):
        self.show_window()
        self.tabs.setCurrentWidget(self.voice_tab)
        self.voice_tab.focus_entry()

    # ── updates ─────────────────────────────────────────────────────────

    def check_updates(self, silent: bool):
        if self._update_worker and self._update_worker.isRunning():
            return
        w = self._update_worker = _UpdateWorker(self.ctx.settings)
        w.found.connect(lambda rel: self._update_found(rel, silent))
        w.failed.connect(lambda msg: self._update_failed(msg, silent))
        w.start()

    def _update_failed(self, msg, silent):
        log(f"update check failed: {msg}")
        if not silent:
            QMessageBox.warning(self, APP_NAME, f"Couldn't check for updates.\n\n{msg}")

    def _update_found(self, rel, silent):
        if rel is None:
            if not silent:
                QMessageBox.information(self, APP_NAME, f"You're up to date (version {__version__}).")
            return
        box = QMessageBox(self)
        box.setWindowTitle(APP_NAME)
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(f"<b>YukiVoice {rel.version}</b> is available (you have {__version__}).")
        if rel.notes.strip():
            box.setInformativeText(rel.notes.strip()[:600])
        if updater.can_self_update() and rel.asset_api_url:
            install = box.addButton("Update and restart", QMessageBox.ButtonRole.AcceptRole)
        else:
            install = box.addButton("Open release page", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        skip = box.addButton("Skip this version", QMessageBox.ButtonRole.DestructiveRole)
        box.exec()
        if box.clickedButton() is skip:
            self.ctx.settings["skipped_version"] = rel.version
        elif box.clickedButton() is install:
            if updater.can_self_update() and rel.asset_api_url:
                self._install_update(rel)
            else:
                QDesktopServices.openUrl(QUrl(rel.url))

    def _install_update(self, rel):
        dlg = QProgressDialog(f"Downloading YukiVoice {rel.version}…", None, 0, 1000, self)
        dlg.setWindowTitle(APP_NAME)
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setValue(0)
        w = self._update_worker = _UpdateWorker(self.ctx.settings, rel)
        w.progress.connect(lambda d, t: dlg.setValue(int(d * 1000 / max(t, 1))))

        def failed(msg):
            dlg.close()
            QMessageBox.warning(self, APP_NAME, f"The update didn't install.\n\n{msg}")

        def done():
            dlg.close()
            updater.relaunch()
            self.quit_app()

        w.failed.connect(failed)
        w.installed.connect(done)
        w.start()

    # ── lifecycle ───────────────────────────────────────────────────────

    def closeEvent(self, e):
        if self.tray and not self._quitting:
            e.ignore()
            self.hide()
            if not self.ctx.settings["tray_hint_shown"]:
                self.ctx.settings["tray_hint_shown"] = True
                self.tray.showMessage(APP_NAME, "Still running in the tray — your virtual mic stays live. "
                                      "Quit from the tray menu.", QSystemTrayIcon.MessageIcon.Information, 5000)
            return
        e.accept()

    def cleanup(self):
        self.audio_tab.cleanup()
        self.voice_tab.cleanup()

    def quit_app(self):
        self._quitting = True
        QApplication.quit()
