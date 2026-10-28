"""Editor for custom voices: blend stock Kokoro voices or import a style file."""

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QMessageBox, QPushButton, QSpinBox, QVBoxLayout)

from .. import tts
from ..audio import player
from ..context import Context

_ROWS = 4


class _Preview(QThread):
    failed = Signal(str)

    def __init__(self, engine, spec):
        super().__init__()
        self.engine, self.spec = engine, spec

    def run(self):
        try:
            lang = self.spec.get("lang", "en-us")
            samples, sr = self.engine.synth(tts.sample_text(lang), self.spec, 1.0, lang)
            player.play_samples(samples, sr, [None]).wait()
        except Exception as e:
            self.failed.emit(str(e))


class CustomVoicesDialog(QDialog):
    def __init__(self, ctx: Context, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Custom voices")
        self.resize(640, 440)
        self.data = tts.load_custom()
        self._file = None       # imported style file of the voice being edited
        self._preview = None

        root = QHBoxLayout(self)
        left = QVBoxLayout()
        self.list = QListWidget()
        self.list.currentTextChanged.connect(self._select)
        left.addWidget(self.list, 1)
        new = QPushButton("New voice")
        new.clicked.connect(self._new)
        left.addWidget(new)
        delete = QPushButton("Delete")
        delete.clicked.connect(self._delete)
        left.addWidget(delete)
        root.addLayout(left, 1)

        right = QVBoxLayout()
        hint = QLabel("Blend up to four voices (weights are relative), or import a Kokoro voice file "
                      "(.npy). The blend is a weighted average of the voices' styles.")
        hint.setObjectName("dim")
        hint.setWordWrap(True)
        right.addWidget(hint)
        row = QHBoxLayout()
        row.addWidget(QLabel("Name"))
        self.name = QLineEdit()
        row.addWidget(self.name, 1)
        right.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Language"))
        self.lang = QComboBox()
        for code, label, _ in tts.LANGUAGES:
            self.lang.addItem(label, code)
        self.lang.setToolTip("The language this voice speaks when Language is set to Auto")
        row.addWidget(self.lang, 1)
        right.addLayout(row)

        self.mix_box = QVBoxLayout()
        self.rows = []
        pack = tts.voice_ids() if tts.is_installed("standard") else []
        for _ in range(_ROWS):
            r = QHBoxLayout()
            combo = QComboBox()
            combo.addItem("—", "")
            for v in pack:
                combo.addItem(f"{tts.describe_voice(v).name} — {tts.describe_voice(v).lang_label}, "
                              f"{tts.describe_voice(v).gender}", v)
            spin = QSpinBox()
            spin.setRange(0, 100)
            spin.setSuffix(" %")
            r.addWidget(combo, 1)
            r.addWidget(spin)
            self.rows.append((combo, spin))
            self.mix_box.addLayout(r)
        right.addLayout(self.mix_box)
        self.file_label = QLabel("")
        self.file_label.setObjectName("dim")
        right.addWidget(self.file_label)
        imp = QPushButton("Import voice file…")
        imp.clicked.connect(self._import)
        right.addWidget(imp)
        right.addStretch(1)

        self.msg = QLabel("")
        self.msg.setObjectName("dim")
        self.msg.setWordWrap(True)
        right.addWidget(self.msg)
        row = QHBoxLayout()
        self.prev = QPushButton("▶  Preview")
        self.prev.clicked.connect(self._play)
        row.addWidget(self.prev)
        save = QPushButton("Save")
        save.setObjectName("go")
        save.clicked.connect(self._save)
        row.addWidget(save)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        right.addLayout(row)
        root.addLayout(right, 2)

        self._fill_list()

    # ── list ────────────────────────────────────────────────────────────

    def _fill_list(self, select=None):
        self.list.blockSignals(True)
        self.list.clear()
        self.list.addItems(sorted(self.data))
        self.list.blockSignals(False)
        names = sorted(self.data)
        if names:
            self.list.setCurrentRow(names.index(select) if select in names else 0)
            self._select(self.list.currentItem().text())
        else:
            self._new()

    def _select(self, name):
        spec = self.data.get(name)
        if spec is None:
            return
        self.name.setText(name)
        self.lang.setCurrentIndex(max(self.lang.findData(spec.get("lang", "en-us")), 0))
        self._file = spec.get("file")
        mix = list((spec.get("mix") or {}).items())
        for i, (combo, spin) in enumerate(self.rows):
            v, w = mix[i] if i < len(mix) else ("", 0)
            combo.setCurrentIndex(max(combo.findData(v), 0))
            spin.setValue(int(round(w * 100)) if w <= 1 else int(w))
        self._show_file()

    def _show_file(self):
        self.file_label.setText(f"Imported voice file in use: {self._file}" if self._file else "")

    def _new(self):
        self.name.setText("")
        self.lang.setCurrentIndex(0)
        self._file = None
        for combo, spin in self.rows:
            combo.setCurrentIndex(0)
            spin.setValue(0)
        self.rows[0][1].setValue(100)
        self._show_file()
        self.name.setFocus()

    def _delete(self):
        item = self.list.currentItem()
        if item and self.data.pop(item.text(), None) is not None:
            tts.save_custom(self.data)
            self._fill_list()
            self.ctx.engine_changed.emit()

    # ── editing ─────────────────────────────────────────────────────────

    def _spec(self):
        spec = {"lang": self.lang.currentData()}
        if self._file:
            spec["file"] = self._file
        else:
            mix = {c.currentData(): s.value() / 100 for c, s in self.rows if c.currentData() and s.value() > 0}
            if not mix:
                raise ValueError("Pick at least one voice with a weight above 0.")
            spec["mix"] = mix
        return spec

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, "Voice file", "", "Kokoro voice (*.npy)")
        if not path:
            return
        try:
            name = self.name.text().strip() or "imported"
            self._file = tts.import_style_file(path, name)
        except Exception as e:
            self.msg.setText(f"Couldn't import: {e}")
            return
        self._show_file()
        self.msg.setText("Imported — give it a name and Save.")

    def _save(self):
        name = self.name.text().strip()
        if not name or ":" in name:
            self.msg.setText("Give the voice a name (no colons).")
            return
        try:
            self.data[name] = self._spec()
        except ValueError as e:
            self.msg.setText(str(e))
            return
        tts.save_custom(self.data)
        self.msg.setText(f"Saved “{name}”.")
        self._fill_list(select=name)
        self.ctx.engine_changed.emit()

    def _play(self):
        if not self.ctx.engine_ready():
            self.msg.setText("Install the voice engine first (Tools → Setup wizard).")
            return
        if self._preview and self._preview.isRunning():
            return
        try:
            spec = self._spec()
        except ValueError as e:
            self.msg.setText(str(e))
            return
        self.msg.setText("Generating…")
        self.prev.setEnabled(False)
        w = self._preview = _Preview(self.ctx.engine(), spec)
        w.failed.connect(lambda m: self.msg.setText(f"Preview failed: {m}"))
        w.finished.connect(lambda: (self.prev.setEnabled(True),
                                    self.msg.setText("") if self.msg.text() == "Generating…" else None))
        w.start()

    def done(self, r):
        if self._preview and self._preview.isRunning():
            self._preview.wait(15000)
        super().done(r)
