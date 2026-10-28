#!/usr/bin/env bash
# Build YukiVoice-x86_64.AppImage. Run from anywhere; needs the build venv's
# python (PY=…) with requirements-build.txt installed.
#   PY=.venv/bin/python packaging/build_appimage.sh
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PY:-python3}"
OUT="${OUT:-dist}"
ARCH=x86_64

"$PY" packaging/make_icons.py >/dev/null
"$PY" -m PyInstaller packaging/yukivoice.spec --noconfirm --distpath "$OUT/pyi" --workpath build/pyi

APPDIR=build/YukiVoice.AppDir
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp -r "$OUT/pyi/yukivoice/." "$APPDIR/usr/bin/"

cp src/yukivoice/assets/icon-256.png "$APPDIR/yukivoice.png"
cp src/yukivoice/assets/icon-256.png "$APPDIR/.DirIcon"
cp src/yukivoice/assets/icon-256.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/yukivoice.png"
cp packaging/yukivoice.desktop "$APPDIR/yukivoice.desktop"
cp packaging/yukivoice.desktop "$APPDIR/usr/share/applications/yukivoice.desktop"

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/yukivoice" "$@"
EOF
chmod +x "$APPDIR/AppRun"

TOOL=build/tools/appimagetool-$ARCH.AppImage
if [ ! -x "$TOOL" ]; then
    mkdir -p build/tools
    curl -fL -o "$TOOL" "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$ARCH.AppImage"
    chmod +x "$TOOL"
fi

mkdir -p "$OUT"
# --appimage-extract-and-run: works where FUSE isn't available (CI containers)
ARCH=$ARCH "$TOOL" --appimage-extract-and-run --no-appstream "$APPDIR" "$OUT/YukiVoice-$ARCH.AppImage"
echo "built $OUT/YukiVoice-$ARCH.AppImage"
