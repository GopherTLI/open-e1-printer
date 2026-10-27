"""Decode a captured 0x1B print job back into a picture (prints ASCII art)."""
import sys

import lzo

sys.path.insert(0, __file__.rsplit("\\", 2)[0])
from e1_replay import JOBS  # noqa: E402

for name, hexstr in JOBS.items():
    f = bytes.fromhex(hexstr)
    hdr, data = f[:17], f[17:-1]
    length, height, blocks = hdr[11] | hdr[12] << 8, hdr[13] | hdr[14] << 8, hdr[15]
    print(f"== {name}: header {hdr.hex(' ')}  len={length} height={height} b15={blocks} lzo={len(data)}B")
    raw = None
    for skip in range(0, 4):
        try:
            raw = lzo.decompress(data[skip:], False, 200000)
            print(f"   decompressed {len(raw)} bytes (skip {skip}, prefix {data[:skip].hex()})")
            break
        except lzo.error:
            pass
    if raw is None:
        print("   could not decompress")
        continue
    bpr = len(raw) // height if height else 0
    print(f"   {bpr} bytes per row -> {bpr * 8} dots wide")
    for r in range(height):
        row = raw[r * bpr:(r + 1) * bpr]
        bits = "".join(f"{b:08b}" for b in row)
        print("   " + bits.replace("0", ".").replace("1", "#"))
