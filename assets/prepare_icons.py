from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "source.png"
OUT_SIZE = 512
TRAY_SIZE = 64
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)

TRAY_VARIANTS = (
    ("tray_gray.png", None),
    ("tray_green.png", (34, 197, 94)),
    ("tray_red.png", (239, 68, 68)),
    ("tray_yellow.png", (255, 193, 7)),
)


def remove_black_background(img: Image.Image, threshold: int = 48) -> Image.Image:
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            mx = max(r, g, b)
            sat = mx - min(r, g, b)
            if mx <= 18 and sat < 35:
                px[x, y] = (0, 0, 0, 0)
                continue
            if mx <= threshold and sat < 42:
                px[x, y] = (0, 0, 0, 0)
                continue
            if mx <= threshold + 30 and sat < 55:
                fade = int(255 * (mx - 18) / max(threshold + 30 - 18, 1))
                fade = max(0, min(255, fade))
                px[x, y] = (r, g, b, min(a, fade))
    return img


def square_logo(path: Path, size: int) -> Image.Image:
    img = Image.open(path).convert("RGBA")
    img = remove_black_background(img)
    bbox = img.getbbox()
    if not bbox:
        raise ValueError(f"No visible content in {path}")
    cropped = img.crop(bbox)
    cw, ch = cropped.size
    side = int(max(cw, ch) * 1.1)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    ox = (side - cw) // 2
    oy = (side - ch) // 2
    canvas.paste(cropped, (ox, oy), cropped)
    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def save_ico(path: Path, base: Image.Image) -> None:
    src = base.convert("RGBA")
    if max(src.size) > 256:
        src = src.resize((256, 256), Image.Resampling.LANCZOS)
    sizes = [(s, s) for s in ICO_SIZES]
    src.save(path, format="ICO", sizes=sizes, bitmap_format="bmp")


def tint_opaque_pixels(
    img: Image.Image, color: tuple[int, int, int], strength: float = 0.38
) -> Image.Image:
    out = img.copy()
    px = out.load()
    cr, cg, cb = color
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = px[x, y]
            if a < 16:
                continue
            t = strength
            px[x, y] = (
                int(r * (1 - t) + cr * t),
                int(g * (1 - t) + cg * t),
                int(b * (1 - t) + cb * t),
                a,
            )
    return out


def tray_icon(base: Image.Image, color: tuple[int, int, int] | None) -> Image.Image:
    small = base.resize((TRAY_SIZE, TRAY_SIZE), Image.Resampling.LANCZOS)
    if color is None:
        return small
    return tint_opaque_pixels(small, color)


def main() -> None:
    if not SOURCE.is_file():
        raise SystemExit(f"Put logo at {SOURCE}")
    base = square_logo(SOURCE, OUT_SIZE)
    base.save(ROOT / "icon.png", format="PNG")
    save_ico(ROOT / "icon.ico", base)
    for fname, rgb in TRAY_VARIANTS:
        tray_icon(base, rgb).save(ROOT / fname, format="PNG")
    print("OK:", ROOT)


if __name__ == "__main__":
    main()
