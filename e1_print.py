"""Design, preview and print labels on a MakeID E1 (WEWIN "new protocol") label printer from a PC.

Previews by default; nothing is sent to the printer without --print.

Examples:
  py e1_print.py "Flour"                         preview a 16 mm label, text auto-sized
  py e1_print.py "Flour" --print                 ...and print it
  py e1_print.py "Spices\\nTop shelf"             two lines (\\n = line break)
  py e1_print.py "Flour" --size 60 --length 40   fixed 60-dot text on a 40 mm label
  py e1_print.py --image logo.png                picture scaled to the printable height
  py e1_print.py --image design.png --raw        print a ready-made design as is (height = tape dots)
  py e1_print.py "Flour" --tape 12               12 mm tape instead of 16 mm
  py e1_print.py "Flour" --copies 3 --print

Outputs (next to this script unless --out-dir is given):
  label.png    the label at real resolution (8 dots/mm, black = printed), as sent to the printer
  preview.png  the label enlarged, on tape-coloured background, with the unprintable edges shaded

Hardware facts (from the decompiled MakeID app and the printer's own status reply):
  203 dpi = 8 dots/mm. The print head is 96 dots (12 mm) across, centred on the tape, so on 16 mm tape
  the outer 2 mm each side can't print. One 0x1B block holds at most 170 rows; longer labels use several.

Job format (OperateNewProtocolPrinterRunnable.operate1BCommand):
  66 <len LE16> 1B | darkness|0x20, 0x03, copies LE16, current copy LE16, 1, label length LE16,
  block rows LE16, blocks still to come, 0 | LZO1X rows of 96 dots (MSB first, 1 = black) | checksum
"""
import argparse
import asyncio
import os

import lzo
from PIL import Image, ImageDraw, ImageFont, ImageOps

from e1_replay import NOTIFY_UUID, find_printer, frame, on_notify, send

from bleak import BleakClient

DOTS_PER_MM = 8
HEAD_DOTS = 96  # printable dots across the tape
DARKNESS = 0x14  # what the app sent (0x34 & 0x1F)
MAX_ROWS = 170  # rows per 0x1B block; the printer reports this in its status reply (bytes 41-42)
HERE = os.path.dirname(os.path.abspath(__file__))


def mm(v):
    return round(v * DOTS_PER_MM)


def printable_band(tape_dots):
    """(top, bottom) rows of the label the head can reach; the head is centred on the tape."""
    p = min(HEAD_DOTS, tape_dots)
    top = (tape_dots - p) // 2
    return top, top + p


def load_font(name, size):
    for candidate in (name, os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", name)):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            pass
    raise SystemExit(f"font not found: {name}")


def text_box(text, font, spacing):
    d = ImageDraw.Draw(Image.new("1", (1, 1)))
    b = d.multiline_textbbox((0, 0), text, font=font, spacing=spacing, align="center")
    return int(b[0]), int(b[1]), int(-(-b[2] // 1)), int(-(-b[3] // 1))  # newer Pillow returns floats


def render_text(text, tape_dots, size, font_name, align, length_dots, margin_dots):
    top, bottom = printable_band(tape_dots)
    band = bottom - top
    inset = 2  # keep ink just off the very edge of the head

    def fits(s):
        f = load_font(font_name, s)
        b = text_box(text, f, spacing=max(1, s // 8))
        w, h = b[2] - b[0], b[3] - b[1]
        ok = h <= band - 2 * inset and (length_dots is None or w <= length_dots - 2 * margin_dots)
        return ok, f, b

    if size:
        _, font, box = fits(size)
        spacing = max(1, size // 8)
    else:
        lo, hi = 6, band
        while lo < hi:  # largest size that fits the printable band (and the fixed length, if any)
            mid = (lo + hi + 1) // 2
            if fits(mid)[0]:
                lo = mid
            else:
                hi = mid - 1
        size = lo
        _, font, box = fits(size)
        spacing = max(1, size // 8)

    w, h = box[2] - box[0], box[3] - box[1]
    # like the web app's auto length: never shorter than the label is tall (at least square)
    length = length_dots if length_dots else max(w + 2 * margin_dots, tape_dots)
    img = Image.new("1", (length, tape_dots), 1)
    if align == "left":
        x = margin_dots
    elif align == "right":
        x = length - margin_dots - w
    else:
        x = (length - w) // 2
    y = top + (band - h) // 2
    ImageDraw.Draw(img).multiline_text(
        (x - box[0], y - box[1]), text, font=font, fill=0, spacing=spacing, align=align
    )
    return img, size


def load_image(path, tape_dots, raw, length_dots, margin_dots):
    img = Image.open(path)
    if img.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGBA", img.size, "white")
        bg.alpha_composite(img.convert("RGBA"))
        img = bg
    img = img.convert("L")
    if raw:
        if img.height != tape_dots:
            raise SystemExit(f"--raw image must be {tape_dots} px tall for this tape (it is {img.height})")
        return img.point(lambda v: 0 if v < 128 else 255).convert("1")
    top, bottom = printable_band(tape_dots)
    band = bottom - top
    scale = band / img.height
    if length_dots:
        scale = min(scale, (length_dots - 2 * margin_dots) / img.width)
    img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
    length = length_dots if length_dots else max(img.width + 2 * margin_dots, tape_dots)
    out = Image.new("L", (length, tape_dots), 255)
    out.paste(img, ((length - img.width) // 2, top + (band - img.height) // 2))
    return out.convert("1")  # dithers greys


def to_head_rows(label):
    """Crop/pad the label (any tape height) to the 96-dot head band, centred."""
    tape_dots = label.height
    top = (tape_dots - HEAD_DOTS) // 2  # negative on tape narrower than the head
    head = Image.new("1", (label.width, HEAD_DOTS), 1)
    head.paste(label.crop((0, max(0, top), label.width, min(tape_dots, top + HEAD_DOTS))), (0, max(0, -top)))
    return head


def make_preview(label, scale=4):
    """Enlarged view: tape background, printable band white, unprintable edges shaded, 1 mm ticks."""
    w, h = label.size
    top, bottom = printable_band(h)
    rgb = Image.new("RGB", (w, h), (255, 255, 255))
    ink = label.convert("L")
    rgb.paste((20, 20, 20), mask=ImageOps.invert(ink))
    big = rgb.resize((w * scale, h * scale), Image.NEAREST)
    shade = Image.new("RGBA", big.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(shade)
    if top > 0:
        d.rectangle((0, 0, big.width, top * scale - 1), fill=(150, 150, 150, 140))
    if bottom < h:
        d.rectangle((0, bottom * scale, big.width, big.height), fill=(150, 150, 150, 140))
    big = Image.alpha_composite(big.convert("RGBA"), shade)
    pad = 12
    canvas = Image.new("RGB", (big.width + 2 * pad, big.height + 2 * pad + 14), (60, 60, 60))
    canvas.paste(big, (pad, pad))
    d = ImageDraw.Draw(canvas)
    d.rectangle((pad - 1, pad - 1, pad + big.width, pad + big.height), outline=(200, 200, 200))
    for x in range(0, w + 1, DOTS_PER_MM):  # ruler: tick every mm, longer every 5 mm
        tick = 8 if (x // DOTS_PER_MM) % 5 == 0 else 4
        d.line((pad + x * scale, pad + big.height + 2, pad + x * scale, pad + big.height + 2 + tick), fill=(200, 200, 200))
    return canvas


def build_job(head, copy=1, copies=1, darkness=DARKNESS):
    """head: PIL image HEAD_DOTS tall, any length, black = print. Returns one 0x1B frame per block."""
    # Rotate so each printer row runs across the tape (matches the decoded app jobs).
    rotated = head.rotate(270, expand=True)  # now HEAD_DOTS wide; letter tops face high dots, as the app does
    rows = rotated.height
    packed = ImageOps.invert(rotated.convert("L")).convert("1").tobytes()  # 1 = black
    bpr = HEAD_DOTS // 8
    blocks = [packed[i * bpr:(i + MAX_ROWS) * bpr] for i in range(0, rows, MAX_ROWS)]
    frames = []
    for n, block in enumerate(blocks):
        height = len(block) // bpr
        header = bytes([
            0x20 | (darkness & 0x1F), 0x03,
            copies & 0xFF, copies >> 8,
            copy & 0xFF, copy >> 8,
            1,
            rows & 0xFF, rows >> 8,  # whole label length
            height & 0xFF, height >> 8,  # rows in this block
            len(blocks) - n - 1,  # blocks still to come
            0,
        ])
        frames.append(frame(0x1B, header + lzo.compress(block, 1, False)))
    return frames


async def print_jobs(jobs):
    dev = await find_printer()
    if not dev:
        raise SystemExit("printer not found - is it on, and not connected to the phone or the web app?")
    replies = asyncio.Queue()

    def handler(sender, data):
        on_notify(sender, data)
        replies.put_nowait(bytes(data))

    async with BleakClient(dev) as client:
        await client.start_notify(NOTIFY_UUID, handler)
        await send(client, frame(0x10, b"\x00"))
        await asyncio.sleep(0.3)
        for c, frames in enumerate(jobs, 1):
            await send(client, frame(0x10, b"\x02"))
            await asyncio.sleep(0.1)
            for n, job in enumerate(frames, 1):
                while not replies.empty():
                    replies.get_nowait()
                await send(client, job)
                print(f"copy {c}/{len(jobs)}: sent block {n}/{len(frames)} ({len(job)} bytes)")
                # The app waits for the printer to answer each block before sending the next.
                try:
                    await asyncio.wait_for(replies.get(), timeout=10)
                except asyncio.TimeoutError:
                    print("   no reply to block, continuing")
            await asyncio.sleep(1.5)
        print("waiting for printer...")
        for _ in range(6):
            await asyncio.sleep(1)
            await send(client, frame(0x10, b"\x00"))
    print("done")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("text", nargs="?", help='label text; "\\n" starts a new line')
    p.add_argument("--image", help="picture to print (scaled to the printable height)")
    p.add_argument("--raw", action="store_true", help="with --image: use it as is; must be tape-height px tall")
    p.add_argument("--tape", type=float, default=16, help="tape width in mm (default 16)")
    p.add_argument("--size", type=int, help="text height in dots (default: as large as fits)")
    p.add_argument("--font", default="ARLRDBD.TTF", help="font file name or path (default ARLRDBD.TTF, Arial Rounded MT Bold)")
    p.add_argument("--align", choices=["center", "left", "right"], default="center")
    p.add_argument("--length", type=float, help="fixed label length in mm (default: fit the content)")
    p.add_argument("--margin", type=float, default=0.5, help="blank tape at each end in mm (default 0.5)")
    p.add_argument("--copies", type=int, default=1)
    p.add_argument("--darkness", type=int, default=DARKNESS, help=f"0-31 (default {DARKNESS})")
    p.add_argument("--out-dir", default=HERE, help="where to write label.png and preview.png")
    p.add_argument("--print", action="store_true", help="send to the printer (otherwise preview only)")
    a = p.parse_args()
    if not a.text and not a.image:
        p.error("give text or --image")

    tape_dots = mm(a.tape)
    length_dots = mm(a.length) if a.length else None
    margin_dots = mm(a.margin)
    if a.image:
        label = load_image(a.image, tape_dots, a.raw, length_dots, margin_dots)
        size = None
    else:
        label, size = render_text(a.text.replace("\\n", "\n"), tape_dots, a.size, a.font, a.align,
                                  length_dots, margin_dots)

    os.makedirs(a.out_dir, exist_ok=True)
    label_path = os.path.join(a.out_dir, "label.png")
    preview_path = os.path.join(a.out_dir, "preview.png")
    label.save(label_path)
    make_preview(label).save(preview_path)
    head = to_head_rows(label)
    clipped = ImageOps.invert(label.convert("L")).getbbox()
    top, bottom = printable_band(tape_dots)
    warn = ""
    if clipped and (clipped[1] < top or clipped[3] > bottom):
        warn = "  WARNING: some ink is outside the printable band and will not print"
    print(f"tape {a.tape:g} mm, label {label.width / DOTS_PER_MM:.1f} mm long ({label.width} dots)"
          + (f", text {size} dots tall" if size else "") + warn)
    print(f"preview: {preview_path}")
    print(f"label:   {label_path}")
    if a.print:
        copies = max(1, a.copies)
        asyncio.run(print_jobs([build_job(head, c, copies, a.darkness) for c in range(1, copies + 1)]))


if __name__ == "__main__":
    main()
