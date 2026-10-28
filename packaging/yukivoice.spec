# PyInstaller spec — Linux: onedir (wrapped into an AppImage), Windows: single-file exe.
#   pyinstaller packaging/yukivoice.spec --noconfirm
import glob
import os
import shutil
import subprocess
import sys

from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
WIN = sys.platform == "win32"

datas = [(os.path.join(ROOT, "src", "yukivoice", "assets"), "yukivoice/assets")]
binaries = []
hiddenimports = ["_miniaudio", "_cffi_backend"]

packages = ["espeakng_loader", "kokoro_onnx", "phonemizer", "pykakasi", "segments", "language_tags", "jaconv", "onnxruntime"]
if WIN:
    packages += ["proctap", "pycaw", "comtypes"]
for pkg in packages:
    try:
        d, b, h = collect_all(pkg)
    except Exception as e:  # optional dependency not installed
        print(f"spec: skipping {pkg}: {e}")
        continue
    datas += d
    binaries += b
    hiddenimports += h

if not WIN:
    # Qt's xcb plugin needs libxcb-cursor, which many distros don't ship by default.
    try:
        out = subprocess.run(["ldconfig", "-p"], capture_output=True, text=True).stdout
        for line in out.splitlines():
            if "libxcb-cursor.so.0" in line and "x86-64" in line:
                binaries.append((line.split("=>")[1].strip(), "."))
                break
    except OSError:
        pass

a = Analysis(
    [os.path.join(ROOT, "packaging", "entry.py")],
    pathex=[os.path.join(ROOT, "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "scipy", "pandas", "PyQt5", "PyQt6", "PySide2",
              "PySide6.QtWebEngineCore", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.Qt3DCore",
              "PySide6.QtCharts", "PySide6.QtMultimedia", "PySide6.QtPdf", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

if WIN:
    exe = EXE(
        pyz, a.scripts, a.binaries, a.datas, [],
        name="YukiVoice",
        icon=os.path.join(ROOT, "src", "yukivoice", "assets", "icon.ico"),
        console=False,
        upx=False,
        runtime_tmpdir=None,
    )
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="yukivoice", console=False, upx=False)
    coll = COLLECT(exe, a.binaries, a.datas, name="yukivoice", upx=False)
