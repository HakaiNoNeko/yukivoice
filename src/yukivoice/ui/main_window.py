"""Main window: Voice and Audio tabs, a Monitor toggle, and a tray icon."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QDesktopServices, QIcon
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QMainWindow, QMenu, QMessageBox,
                               QSystemTrayIcon, QTabWidget, QVBoxLayout, QWidget)

from .. import APP_NAME, __version__, config
from ..context import Context
from . import theme
from .audio_tab import AudioTab
from .voice_tab import VoiceTab

_DOT = {"ready": theme.OK, "busy": theme.ACCENT, "warn": theme.WARN, "off": theme.DIM}


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
        self._build_menu()
        self.tray = self._build_tray(icon)

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
        from PySide6.QtWidgets import QApplication
        QApplication.quit()
