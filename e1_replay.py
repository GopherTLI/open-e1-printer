"""Replay captured MakeID E1 print jobs from a PC over BLE.

Protocol (from HCI snoop capture):
  frame = 0x66, length (uint16 LE, whole frame), cmd, payload..., checksum
  checksum makes the sum of all frame bytes == 0 (mod 256)
  PC -> printer: write-without-response on ABF1
  printer -> PC: notifications on ABF2

  cmd 0x10 [00]  status poll (app sends once per second)
  cmd 0x10 [02]  status poll sent right before a print
  cmd 0x50       firmware / serial info
  cmd 0x1B       print job (header + compressed bitmap)

Usage:  py e1_replay.py [info|blank|A|AB]
Close the MakeID app / nRF Connect first: the printer takes one connection at a time.
"""
import asyncio
import os
import sys

from bleak import BleakClient, BleakScanner

# Printers advertise as "E1" + serial (e.g. E123E0xxxx). Set E1_ADDRESS to pick one when several are near.
ADDRESS = os.environ.get("E1_ADDRESS")
NAME_PREFIX = "E1"
WRITE_UUID = "0000abf1-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000abf2-0000-1000-8000-00805f9b34fb"
CHUNK = 58  # same chunk size the app used

JOBS = {
    "blank": "6622001b3403010001000158005800000002000000000020000000fd000011000043",
    "A": "6610011b340301000100015800580000000200001000002702001e002802001f80292d00f0292d00fc292d00ff2893001ffff02763001ffffc272e0007ff299100ff2991003f389100e027f4002a92003fff2827013fffff2791003f29bb013f03ff2793003f00ff2792003f00289000023f0003ffffc40c013f00007ff004013f00001ffc13013f000003292f00007ff0a006023f0000003f282d0001298d000f292d007f282e0001ffe3123f000f27ca033f00278900002bcf020ffffea70d00003f288900002cec03278800291401020003ffffc0e9071f28160100ffed11003789001f288a00001f281601001f28a301001ff8f30b00001f27a0010100001e0028020018002000b0000011000042",
    "AB": "66b3011b340301000100016700670000000200001000002702001e002802001f80292d00f0292d00fc292d00ff2893001ffff02763001ffffc272e0007ff299100ff2991003f389100e027f4002a92003fff2827013fffff2791003f29bb013f03ff2793003f00ff2792003f00289000023f0003ffffc40c013f00007ff004013f00001ffc13013f000003292f00007ff0a006023f0000003f282d0001298d000f292d007f282e0001ffe3123f000f27ca033f00278900002bcf020ffffea70d00003f288900002cec03278800291401020003ffffc0e9071f28160100ffed11003789001f288a00001f281601001f28a301001ff8f30b00001f27a0010100001e002802001800204902001fff800002f00000000020282c0003800003f00003ac0a20802d0007ff1407f000ce01c0002b2c000cf80007e0000000000fc00007fc000faf01e0000f272c0003f0001ffe001f9c020407f8001fff807f843b0307fc007fffffa0410307ff83ff3fffac580203ffffff1fcc010401fffffe0fffffa03e03fffffc0ffffeac01037ffff803fff8ac01033ffff001fff0ac01021fffe0003faa010003bc09d401202e1800110000e9",
}


def frame(cmd, payload=b""):
    body = bytes([0x66]) + (len(payload) + 5).to_bytes(2, "little") + bytes([cmd]) + payload
    return body + bytes([(-sum(body)) & 0xFF])


def on_notify(_, data: bytearray):
    print("<-", data.hex())
    if len(data) > 4 and data[3] == 0x50:
        print("   info:", [s.decode(errors="replace") for s in data[4:-1].split(b"\x00") if s])


async def send(client, data):
    for i in range(0, len(data), CHUNK):
        await client.write_gatt_char(WRITE_UUID, data[i:i + CHUNK], response=False)
        await asyncio.sleep(0.015)


async def find_printer(timeout=10):
    if ADDRESS:
        return await BleakScanner.find_device_by_address(ADDRESS, timeout=timeout)
    return await BleakScanner.find_device_by_filter(
        lambda d, ad: (d.name or ad.local_name or "").startswith(NAME_PREFIX), timeout=timeout)


async def main(which):
    print("scanning...")
    dev = await find_printer()
    if not dev:
        sys.exit("printer not found - is it on, and disconnected from the phone?")
    async with BleakClient(dev) as client:
        print("connected")
        await client.start_notify(NOTIFY_UUID, on_notify)
        await send(client, frame(0x10, b"\x00"))
        await asyncio.sleep(0.3)
        await send(client, frame(0x50))
        await asyncio.sleep(0.5)
        if which != "info":
            await send(client, frame(0x10, b"\x02"))
            await asyncio.sleep(0.1)
            await send(client, bytes.fromhex(JOBS[which]))
            print("job sent, waiting for printer...")
            for _ in range(8):
                await asyncio.sleep(1)
                await send(client, frame(0x10, b"\x00"))


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "info"
    if which not in ("info", *JOBS):
        sys.exit("usage: py e1_replay.py [info|blank|A|AB]")
    asyncio.run(main(which))
