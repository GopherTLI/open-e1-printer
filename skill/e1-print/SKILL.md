---
name: e1-print
description: Design and print labels on the user's MakeID E1 Bluetooth label printer. Use whenever the user asks to print, make or design a label, sticker or tag on the E1 / label maker / label printer (e.g. "print Flour on the E1", "make me labels for my spice jars", "label this cable"). Always shows a preview first and prints only after the user says to.
---

# Print labels on the MakeID E1

The user's MakeID E1 is driven by a custom Python driver in this repo (set the path below to where you cloned it)
(`e1_print.py`, protocol notes in its docstring). It renders the label, writes a preview, and only sends
to the printer with `--print`.

## Workflow (always in this order)

1. **Design.** Work out what the user wants: text, lines, layout, size, length, copies. Assume **16 mm tape**
   unless they name another width (`--tape 12`, `--tape 9`). Don't ask about things you can sensibly
   decide; pick good defaults (Arial Rounded MT Bold, centered, text as large as fits, 0.5 mm end margin).
2. **Render a preview** (no `--print`), into a fresh folder per request:
   ```
   cd <path-to>\open-e1-printer
   py e1_print.py "Flour" --out-dir previews\<short-name>
   ```
3. **Check it yourself first**: Read `preview.png` and look at it. Fix anything clipped, cramped, off-center
   or outside the white printable band (the script prints a WARNING for ink outside it) before showing it.
4. **Show the user** `preview.png` (SendUserFile with display "render"), plus one line: tape width, label
   length in mm, copies. Then ask: fix or print?
5. **Fix** → change the design, re-render, show again. **Print** → only on the user's explicit go-ahead
   for that preview, run the same command with `--print` (and `--copies N` if asked). Each new or changed
   design needs a new preview and a new go-ahead.
6. Report what the script printed ("done", or the error).

## e1_print.py options

| Option | Meaning |
|---|---|
| `"text"` | Label text. `\n` inside the string = new line. |
| `--tape MM` | Tape width, default 16. |
| `--size DOTS` | Text height in dots (8 dots = 1 mm). Default: largest that fits. |
| `--font FILE` | Any font in C:\Windows\Fonts or a path. Default `ARLRDBD.TTF` (Arial Rounded MT Bold); `arialbd.ttf` for plain Arial Bold. E.g. `arial.ttf`, `consola.ttf`, `segoeuib.ttf`, `seguiemj.ttf` (emoji, renders black). |
| `--align center/left/right` | For multi-line text and fixed lengths. |
| `--length MM` | Fixed label length. Default: fit content + margins, but never shorter than the tape is wide (16 mm tape → at least 16 mm long), like the web app's auto length. |
| `--margin MM` | Blank tape at each end, default 0.5. |
| `--image FILE` | Print a picture, scaled to the printable height (greys are dithered). |
| `--image FILE --raw` | Print a ready-made design as is. Must be exactly tape-height px tall (16 mm = 128 px). |
| `--copies N` | Number of copies. |
| `--darkness 0-31` | Print darkness, default 20. Raise if prints are faint. |
| `--out-dir DIR` | Where `label.png` and `preview.png` go. |
| `--print` | Actually print. |

## Hardware facts that matter for design

- 203 dpi = **8 dots per mm**. Label height on 16 mm tape = 128 dots.
- The print head is **96 dots (12 mm)** wide, centred on the tape. On 16 mm tape the outer **2 mm on each
  side can't print** (shaded grey in the preview). Keep everything in the white band.
- Long labels are fine; the driver splits them into 170-row blocks automatically.

## Custom layouts (anything the CLI options can't do)

For icons plus text, boxes, QR codes, barcodes, mixed font sizes, columns, etc., draw the label yourself
with Pillow in a small script saved in the request's preview folder, then print it with `--raw`:

- Canvas: `Image.new("1", (length_dots, 128), 1)` for 16 mm tape (white = 1, black = 0).
- Keep ink inside rows 16-111 (the printable band on 16 mm tape).
- QR codes: `py -m pip install qrcode` if missing; scale with NEAREST so modules stay crisp, quiet zone ≥ 2 dots.
- Then: `py e1_print.py --image previews\<name>\design.png --raw --out-dir previews\<name>` and continue
  from step 3. Run scripts with `py`, not `python` (`python` isn't on PATH here).

## Photos and artwork

Only 96 dots of height print, so whole scenes turn to noise. What works (see
`tools/art_label.py`):
- Crop tight to the subject; show the user a preview before going further.
- For more detail, lay the subject sideways so its long axis runs along the tape (any length), roughly
  doubling the dots; offer this when detail matters, since it's less recognizable at a glance.
- Autocontrast, a little extra contrast, then UnsharpMask (radius ~1.2, percent ~160) before dithering.
- Atkinson dithering (spreads 6/8 of the error) keeps highlights clean; Pillow's default Floyd-Steinberg
  speckles them.
- Public-domain art: fetch a modest-size copy (e.g. 800 px) from Wikimedia Commons via Special:FilePath into
  the request's preview folder.

## If printing fails

- **"printer not found"**: the printer is off, out of range, or still connected to something else. The E1
  takes one connection at a time: the phone's MakeID app, nRF Connect or the NiimBlue web app
  (Chrome tab at localhost:5173) may be holding it. Ask the user to disconnect it or close that tab,
  turn the printer on, then retry.
- **Blank or faint print**: raise `--darkness` (e.g. 26).
- **Part of the label missing**: re-check the preview for ink outside the printable band.
- Never change the protocol code in `e1_print.py` / `e1_replay.py` to work around a failure without
  telling the user; it was reverse-engineered and verified against real prints.
