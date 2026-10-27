"""Micro-USB cable flag: hollow connector-face outline on each 20 mm flag, 12 mm blank wrap in the middle.

Drawn at SS x resolution with rounded joins, then scaled down and thresholded, so the chamfers step evenly.
"""
import os

from PIL import Image, ImageDraw, ImageFilter

DOTS = 8  # per mm
SS = 8  # supersampling
FLAG, WRAP, TAPE = 20 * DOTS, 12 * DOTS, 128
BAND_TOP, BAND_BOTTOM = 16, 112  # printable rows on 16 mm tape

big = Image.new("L", ((2 * FLAG + WRAP) * SS, TAPE * SS), 255)
d = ImageDraw.Draw(big)


def plug(cx):
    # micro-B face: 6.8 x 1.8 mm, lower corners chamfered; drawn ~16x scale
    w, h, cham, wall = 128, 46, 17, 10
    cy = (BAND_TOP + BAND_BOTTOM) / 2
    # centre line of the outline, inset by half the wall so the outside matches w x h
    i = wall / 2
    x0, x1, y0, y1 = cx - w / 2 + i, cx + w / 2 - i, cy - h / 2 + i, cy + h / 2 - i
    c = cham - i * 0.4
    pts = [(x0, y0), (x1, y0), (x1, y1 - c), (x1 - c, y1), (x0 + c, y1), (x0, y1 - c), (x0, y0)]
    pts = [(x * SS, y * SS) for x, y in pts]
    d.line(pts, fill=0, width=wall * SS, joint="curve")
    r = wall * SS / 2  # round the start/end join too
    d.ellipse((pts[0][0] - r, pts[0][1] - r, pts[0][0] + r, pts[0][1] + r), fill=0)


plug(FLAG / 2)
plug(FLAG + WRAP + FLAG / 2)
# soften every corner (inside and out) for a rounder, cartoon look
big = big.filter(ImageFilter.GaussianBlur(1.8 * SS)).point(lambda v: 0 if v < 128 else 255)
small = big.resize((big.width // SS, big.height // SS), Image.LANCZOS)
small.point(lambda v: 0 if v < 128 else 255).convert("1").save(os.path.join(os.path.dirname(__file__), "design.png"))
