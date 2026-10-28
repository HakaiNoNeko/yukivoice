"""Build every icon format from one source PNG (assets/icon.png).

    python packaging/make_icons.py                # re-derive icon.ico + sized PNGs
    python packaging/make_icons.py --placeholder  # draw a stand-in icon first
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ASSETS = Path(__file__).resolve().parent.parent / "src" / "yukivoice" / "assets"
SRC = ASSETS / "icon.png"


def placeholder(size=1024):
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.22), fill=(13, 13, 26, 255))
    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    cyan, white, violet = (60, 220, 255, 255), (240, 244, 255, 255), (123, 110, 246, 255)
    # cat ears
    for sign in (-1, 1):
        cx = s // 2 + sign * int(s * 0.19)
        pts = [(cx - int(s * 0.11), int(s * 0.36)), (cx + sign * int(s * 0.07), int(s * 0.09)),
               (cx + int(s * 0.11), int(s * 0.36))]
        d.polygon(pts, fill=white)
        inner = [(x + (cx - x) * 0.0, y) for x, y in pts]
        g.polygon([(cx - int(s * 0.06), int(s * 0.34)), (cx + sign * int(s * 0.045), int(s * 0.16)),
                   (cx + int(s * 0.06), int(s * 0.34))], fill=cyan)
    # mic capsule + stand
    g.rounded_rectangle((s * 0.38, s * 0.30, s * 0.62, s * 0.62), radius=int(s * 0.12), outline=cyan, width=int(s * 0.03))
    g.arc((s * 0.28, s * 0.42, s * 0.72, s * 0.76), 20, 160, fill=cyan, width=int(s * 0.03))
    g.line((s * 0.5, s * 0.76, s * 0.5, s * 0.86), fill=cyan, width=int(s * 0.03))
    g.line((s * 0.40, s * 0.86, s * 0.60, s * 0.86), fill=cyan, width=int(s * 0.03))
    for k, x in enumerate((0.15, 0.22, 0.78, 0.85)):
        h = (0.10, 0.18, 0.18, 0.10)[k]
        g.line((s * x, s * (0.52 - h / 2), s * x, s * (0.52 + h / 2)), fill=violet, width=int(s * 0.025))
    blur = glow.filter(ImageFilter.GaussianBlur(s * 0.012))
    img = Image.alpha_composite(img, blur)
    img = Image.alpha_composite(img, glow)
    return img


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    if "--placeholder" in sys.argv:
        placeholder().save(SRC)
    img = Image.open(SRC).convert("RGBA")
    if img.width != img.height:                     # centre-crop to a square
        m = min(img.size)
        img = img.crop(((img.width - m) // 2, (img.height - m) // 2, (img.width + m) // 2, (img.height + m) // 2))
    img = img.resize((1024, 1024), Image.LANCZOS)
    img.save(SRC)
    img.save(ASSETS / "icon.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    img.resize((256, 256), Image.LANCZOS).save(ASSETS / "icon-256.png")
    print("wrote", [p.name for p in sorted(ASSETS.iterdir())])


if __name__ == "__main__":
    main()
