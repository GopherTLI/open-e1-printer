"""Turn a photo or painting into a 1-bit E1 label design (16 mm tape, 96-dot printable band).

  py tools\art_label.py SRC OUT.png --crop L T R B [--sideways] [--tape 16]

--crop takes fractions of the source (0-1): left top right bottom.
--sideways lays the crop along the tape (top of the subject toward the left end) for ~2x the dots.
Then: py e1_print.py --image OUT.png --raw
"""
import argparse

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

HEAD = 96


def atkinson(img):
    """Atkinson dithering: spreads only 6/8 of the error, so highlights stay clean."""
    w, h = img.size
    px = [list(map(float, img.crop((0, y, w, y + 1)).getdata())) for y in range(h)]
    out = Image.new("1", (w, h), 1)
    for y in range(h):
        for x in range(w):
            old = px[y][x]
            new = 255.0 if old >= 128 else 0.0
            if not new:
                out.putpixel((x, y), 0)
            err = (old - new) / 8
            for dx, dy in ((1, 0), (2, 0), (-1, 1), (0, 1), (1, 1), (0, 2)):
                if 0 <= x + dx < w and y + dy < h:
                    px[y + dy][x + dx] += err
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("src")
    p.add_argument("out")
    p.add_argument("--crop", type=float, nargs=4, default=(0, 0, 1, 1), metavar=("L", "T", "R", "B"))
    p.add_argument("--sideways", action="store_true")
    p.add_argument("--tape", type=float, default=16)
    p.add_argument("--margin", type=int, default=4, help="dots at each end")
    a = p.parse_args()

    tape = round(a.tape * 8)
    band = min(HEAD, tape)
    top = (tape - band) // 2
    src = Image.open(a.src).convert("L")
    w, h = src.size
    l, t, r, b = a.crop
    fig = src.crop((int(w * l), int(h * t), int(w * r), int(h * b)))
    if a.sideways:
        fig = fig.rotate(90, expand=True)
    fig = fig.resize((max(1, round(fig.width * band / fig.height)), band), Image.LANCZOS)
    fig = ImageOps.autocontrast(fig, cutoff=1)
    fig = ImageEnhance.Contrast(fig).enhance(1.2)
    fig = fig.filter(ImageFilter.UnsharpMask(radius=1.2, percent=160, threshold=2))
    dots = atkinson(fig)
    length = max(dots.width + 2 * a.margin, tape)  # at least square, like the default labels
    label = Image.new("1", (length, tape), 1)
    label.paste(dots, ((length - dots.width) // 2, top))
    label.save(a.out)
    print(f"{a.out}: {length} x {tape} dots ({length / 8:.1f} mm long)")


if __name__ == "__main__":
    main()
