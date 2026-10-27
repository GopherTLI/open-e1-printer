# open-e1-printer

Print anything on a **MakeID E1** Bluetooth label printer from a PC, without the vendor app.
A small Python driver plus tools, built by reverse-engineering the printer's Bluetooth LE protocol.

> **Unofficial.** Not affiliated with or endorsed by MakeID or WEWIN. MakeID is a trademark of its owner.
> No vendor code is included; everything here was written from scratch from observed traffic.

## Quick start

```bash
pip install bleak pillow python-lzo        # Python 3.9: pip install "bleak==0.22.3"
python e1_print.py "Flour"                 # writes preview.png, prints nothing
python e1_print.py "Flour" --print         # prints it
```

Close the MakeID app (or anything else connected to the printer) first; it accepts one connection at a time.
The printer is found automatically (Bluetooth name starting with `E1`); set `E1_ADDRESS` to choose one.

### More examples

```bash
python e1_print.py "Spices\nTop shelf"               # two lines
python e1_print.py "Flour" --font comicbd.ttf          # any installed font
python e1_print.py "Flour" --length 40 --align left    # fixed 40 mm label
python e1_print.py "Flour" --tape 12                    # 12 mm tape (default 16)
python e1_print.py --image logo.png                     # a picture, dithered to fit
python e1_print.py --image design.png --raw             # a ready-made 1-bit design (128 px tall on 16 mm tape)
python e1_print.py "Flour" --copies 3 --print
```

`preview.png` shows the label enlarged, with the edges the print head can't reach shaded and a 1 mm ruler.

## Tools

| File | What it does |
|---|---|
| `e1_print.py` | Render, preview and print text or images. |
| `e1_replay.py` | Protocol basics; replays three captured jobs (`python e1_replay.py info` prints firmware/serial). |
| `tools/art_label.py` | Turn a photo or painting into a crisp 1-bit label (crop, sharpen, Atkinson dither). |
| `tools/parse_snoop.py` | Decode an Android `btsnoop_hci.log` into readable ATT traffic. |
| `tools/extract_jobs.py` | Pull complete print jobs out of decoded traffic. |
| `tools/decode_job.py` | Decompress print jobs back into ASCII-art images. |
| `examples/cable_flag.py` | A wrap-around cable flag with a drawn icon (custom layout example). |
| `skill/e1-print/` | A [Claude Code](https://claude.com/claude-code) skill: ask for a label in plain words, get a preview, approve, print. |

## Hardware

- 203 dpi (8 dots/mm). The print head is **96 dots (12 mm)** wide, centred on the tape, so on 16 mm tape
  the outer 2 mm each side can't print.
- Tape widths 9-16 mm, continuous.

## Protocol

Bluetooth LE, no pairing or authentication.

| Characteristic | Role |
|---|---|
| service `0xABF0` | |
| `0xABF1` | write without response: commands to the printer |
| `0xABF2` | notify: replies from the printer |

Every packet (both directions):

```
66 | length (uint16 LE, whole packet) | command | payload... | checksum
```

The checksum is chosen so that all bytes of the packet sum to 0 (mod 256). The app sends in 58-byte writes.

| Command | Payload | Meaning |
|---|---|---|
| `0x10` | `00` | Status poll (the app sends one per second). Reply is 44 bytes; bytes 39-40 = head width in bytes (12), bytes 41-42 = max rows per print block (170). |
| `0x10` | `02` | Status poll sent just before a print. |
| `0x50` | - | Device info: firmware strings and serial, NUL-separated. |
| `0x1B` | see below | Print one block of the image. |

`0x1B` payload:

| Byte | Meaning |
|---|---|
| 0 | darkness (low 5 bits, app uses 20) \| `0x20` |
| 1 | cut/save mode, app sends `0x03` |
| 2-3 | total copies (LE) |
| 4-5 | current copy (LE) |
| 6 | `0x01` |
| 7-8 | whole label length in rows (LE) |
| 9-10 | rows in this block (LE) |
| 11 | blocks still to come after this one |
| 12 | `0x00` |
| 13... | LZO1X-compressed bitmap |

The bitmap is rows of 96 dots (12 bytes, MSB first, 1 = black). Each row runs **across** the tape and
rows advance along its length, with the tops of letters toward the high dots. Labels longer than the
printer's block limit (170 rows) are split into several `0x1B` packets, waiting for the printer's reply
to each before sending the next. Any valid LZO1X stream works, including one that stores the data as
a single literal run.

## How it was worked out

1. Listed the GATT services with nRF Connect.
2. Captured the vendor app printing a blank label, "A" and "AB" with Android's Bluetooth HCI snoop log,
   decoded with `tools/parse_snoop.py`.
3. Spotted the `0x66` framing and zero-sum checksum, replayed the captured jobs from a PC (`e1_replay.py`).
4. Identified the image compression as LZO1X and the header fields, then confirmed by decompressing the
   captured jobs back into the original letters (`tools/decode_job.py`).
5. Found the 170-row block limit when long labels came out truncated; the printer reports it in its
   status reply.

## License

MIT, see [LICENSE](LICENSE).
