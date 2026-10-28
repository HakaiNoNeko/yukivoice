"""Dark violet theme (same palette as the original YukiVoice/YukiAudio)."""

BG = "#0d0d1a"
CARD = "#13132b"
BORDER = "#2a2a50"
ACCENT = "#7b6ef6"
ACCENT_HI = "#a89cf7"
TEXT = "#dde1f0"
DIM = "#6b6b8a"
OK = "#6ef7a0"
WARN = "#f7d06e"
ERR = "#f76e6e"

QSS = f"""
* {{ color: {TEXT}; }}
QWidget {{ background-color: {BG}; font-size: 10pt; }}
QMainWindow, QDialog, QWizard, QWizardPage {{ background-color: {BG}; }}
QLabel {{ background: transparent; }}
QLabel#title {{ color: {ACCENT_HI}; font-weight: bold; font-size: 15pt; }}
QLabel#section {{ color: {ACCENT_HI}; font-weight: bold; }}
QLabel#dim {{ color: {DIM}; font-size: 9pt; }}
QLabel#ok {{ color: {OK}; }}
QLabel#warn {{ color: {WARN}; }}
QLabel#err {{ color: {ERR}; }}

QFrame#card {{ background-color: {CARD}; border: 1px solid {BORDER}; border-radius: 6px; }}
QFrame#card QLabel, QFrame#card QCheckBox {{ background: transparent; }}

QTextEdit, QListWidget {{
    background-color: {CARD}; border: 1px solid {BORDER}; border-radius: 6px;
    padding: 6px; selection-background-color: {ACCENT};
}}
QLineEdit {{
    background-color: {CARD}; border: 1px solid {BORDER}; border-radius: 4px;
    padding: 6px 10px; font-size: 11pt; selection-background-color: {ACCENT};
}}
QLineEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}

QComboBox {{
    background-color: {CARD}; border: 1px solid {BORDER}; border-radius: 4px;
    padding: 5px 8px; min-height: 18px;
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background-color: {CARD}; border: 1px solid {BORDER};
    selection-background-color: {ACCENT}; outline: none;
}}

QPushButton {{
    background-color: {CARD}; border: 1px solid {BORDER}; border-radius: 4px; padding: 6px 14px;
}}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:disabled {{ color: {DIM}; }}
QPushButton#go {{ background-color: {ACCENT}; border: none; color: white; font-weight: bold; }}
QPushButton#go:hover {{ background-color: {ACCENT_HI}; }}
QPushButton#go:disabled {{ background-color: {BORDER}; color: {DIM}; }}
QPushButton#stop {{ background-color: {ERR}; border: none; color: white; font-weight: bold; }}

QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 6px; top: -1px; }}
QTabBar::tab {{
    background: {BG}; border: 1px solid {BORDER}; border-bottom: none;
    padding: 7px 22px; margin-right: 3px; border-top-left-radius: 6px; border-top-right-radius: 6px;
    color: {DIM};
}}
QTabBar::tab:selected {{ background: {CARD}; color: {ACCENT_HI}; font-weight: bold; }}
QTabBar::tab:hover:!selected {{ color: {TEXT}; }}

QProgressBar {{
    background-color: {CARD}; border: 1px solid {BORDER}; border-radius: 4px;
    text-align: center; min-height: 18px;
}}
QProgressBar::chunk {{ background-color: {ACCENT}; border-radius: 3px; }}

QCheckBox, QRadioButton {{ background: transparent; spacing: 6px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 15px; height: 15px; border: 1px solid {BORDER}; background: {CARD};
}}
QCheckBox::indicator {{ border-radius: 3px; }}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT_HI}; }}

QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {ACCENT}; width: 14px; margin: -6px 0; border-radius: 7px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}

QMenuBar {{ background: {BG}; }}
QMenuBar::item:selected {{ background: {CARD}; }}
QMenu {{ background: {CARD}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 5px 22px; }}
QMenu::item:selected {{ background: {ACCENT}; }}
QToolTip {{ background: {CARD}; border: 1px solid {ACCENT}; padding: 4px; }}

QScrollBar:vertical {{ background: {BG}; width: 10px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
"""
