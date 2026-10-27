import struct, sys

path = sys.argv[1]
data = open(path, 'rb').read()
assert data[:8] == b'btsnoop\x00', data[:8]
dlt = struct.unpack('>I', data[12:16])[0]
off = 16
pending = {}  # acl handle -> (dir, buf, expected)
out = []
char_map = {}  # value handle -> uuid

def att(direction, ts, pdu):
    op = pdu[0]
    if op == 0x09 and len(pdu) > 2 and pdu[1] in (7, 21):  # read by type resp (char decl)
        ln = pdu[1]
        for i in range(2, len(pdu) - ln + 1, ln):
            e = pdu[i:i+ln]
            vh = struct.unpack('<H', e[3:5])[0]
            u = e[5:]
            if len(u) not in (2, 16):
                continue
            char_map[vh] = u[::-1].hex() if len(u) == 16 else '%04x' % struct.unpack('<H', u)[0]
    out.append((ts, direction, op, pdu))

n = 0
while off + 24 <= len(data):
    olen, ilen, flags, drops, ts = struct.unpack('>IIIIq', data[off:off+24])
    rec = data[off+24:off+24+ilen]
    off += 24 + ilen
    n += 1
    direction = 'RX' if flags & 1 else 'TX'
    if dlt == 1002:
        if rec and rec[0] == 0x04 and len(rec) > 4 and rec[1] == 0x3e and rec[3] in (0x01, 0x0a):
            ch = struct.unpack('<H', rec[5:7])[0]
            addr = ':'.join('%02X' % b for b in rec[9:15][::-1])
            out.append((ts, 'EV', 0xff, ('CONN acl=0x%03x peer=%s' % (ch, addr)).encode()))
            continue
        if not rec or rec[0] != 0x02:
            continue
        rec = rec[1:]
    elif dlt != 1001:
        continue
    if len(rec) < 4:
        continue
    hh, alen = struct.unpack('<HH', rec[:4])
    h = hh & 0x0fff
    pb = (hh >> 12) & 3
    payload = rec[4:4+alen]
    key = (h, direction)
    if pb == 1:
        if key in pending:
            pending[key][1] += payload
    else:
        if len(payload) < 4:
            continue
        l2len, cid = struct.unpack('<HH', payload[:4])
        pending[key] = [cid, payload[4:], l2len, ts]
    if key in pending:
        cid, buf, l2len, t0 = pending[key]
        if len(buf) >= l2len:
            del pending[key]
            if cid == 4:
                att('%s@%03x' % (direction, h), t0, bytes(buf[:l2len]))

names = {0x12: 'WRITE_REQ', 0x52: 'WRITE_CMD', 0x1b: 'NOTIFY', 0x1d: 'INDICATE',
         0x0a: 'READ_REQ', 0x0b: 'READ_RSP', 0x13: 'WRITE_RSP', 0x02: 'MTU_REQ', 0x03: 'MTU_RSP'}
print('records', n, 'dlt', dlt)
print('char map', {hex(k): v for k, v in char_map.items()})
t_base = out[0][0] if out else 0
for ts, d, op, pdu in out:
    if op == 0xff:
        print('%9.3f %s' % ((ts - t_base) / 1e6, pdu.decode()))
        continue
    if op not in names:
        continue
    extra = ''
    body = pdu[1:]
    if op in (0x12, 0x52, 0x1b, 0x1d, 0x0a):
        hnd = struct.unpack('<H', pdu[1:3])[0]
        extra = 'h=0x%04x(%s) ' % (hnd, char_map.get(hnd, '?'))
        body = pdu[3:]
    print('%9.3f %s %-9s %slen=%d %s' % ((ts - t_base) / 1e6, d, names[op], extra, len(body), body.hex()))
