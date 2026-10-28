"""Derive every icon format from the source artwork (assets/icon-source.png, a
square image drawn edge to edge). Run before packaging; safe to re-run.

    python packaging/make_icons.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parent.parent / "src" / "yukivoice" / "assets"
SOURCE = ASSETS / "icon-source.png"
RADIUS = 0.2  # corner radius as a fraction of the side


def rounded(img: Image.Image) -> Image.Image:
    size = img.width
    scale = 4  # supersample the mask for smooth edges
    mask = Image.new("L", (size * scale, size * scale), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size * scale - 1, size * scale - 1),
                                           radius=int(size * scale * RADIUS), fill=255)
    img = img.copy()
    img.putalpha(mask.resize((size, size), Image.LANCZOS))
    return img


def main():
    src = Image.open(SOURCE).convert("RGB")
    m = min(src.size)
    src = src.crop(((src.width - m) // 2, (src.height - m) // 2, (src.width + m) // 2, (src.height + m) // 2))
    icon = rounded(src.resize((1024, 1024), Image.LANCZOS))
    icon.save(ASSETS / "icon.png")
    icon.save(ASSETS / "icon.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    icon.resize((256, 256), Image.LANCZOS).save(ASSETS / "icon-256.png")
    print("wrote", sorted(p.name for p in ASSETS.iterdir()))


if __name__ == "__main__":
    main()
