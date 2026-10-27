import sys, re
jobs = []; cur = None
for line in open(sys.argv[1]):
    m = re.search(r'TX@043 WRITE_CMD h=0x000d\(abf1\) len=\d+ (\w+)', line)
    if not m: continue
    b = bytes.fromhex(m.group(1))
    if cur is not None:
        cur += b
        if len(cur) >= need: jobs.append(cur[:need]); cur = None
        continue
    if b[0] == 0x66 and b[3] == 0x1b:
        need = b[1] | b[2] << 8; cur = bytearray(b)
        if len(cur) >= need: jobs.append(cur[:need]); cur = None
for j in jobs:
    print(len(j), sum(j) & 0xff, bytes(j).hex())
