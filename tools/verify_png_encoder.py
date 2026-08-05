#!/usr/bin/env python3
"""Verify the deterministic encoder golden with Python's maintained zlib."""

import binascii
import struct
import zlib


GOLDEN = bytes.fromhex(
    "89504e470d0a1a0a"
    "0000000d49484452000000010000000108060000001f15c489"
    "00000010494441547801010500faff0012345678020d0115b2641ec4"
    "0000000049454e44ae426082"
)
SIGNATURE = b"\x89PNG\r\n\x1a\n"
RAW = b"\x00\x12\x34\x56\x78"


def chunk(kind: bytes, payload: bytes) -> bytes:
    checksum = binascii.crc32(kind + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)


def independently_constructed() -> bytes:
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    stored = b"\x01" + struct.pack("<HH", len(RAW), (~len(RAW)) & 0xFFFF) + RAW
    stream = b"\x78\x01" + stored + struct.pack(">I", zlib.adler32(RAW) & 0xFFFFFFFF)
    return SIGNATURE + chunk(b"IHDR", ihdr) + chunk(b"IDAT", stream) + chunk(b"IEND", b"")


def parse_chunks(data: bytes) -> dict[bytes, list[bytes]]:
    assert data.startswith(SIGNATURE)
    result: dict[bytes, list[bytes]] = {}
    offset = len(SIGNATURE)
    while offset < len(data):
        size = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + size]
        checksum = struct.unpack_from(">I", data, offset + 8 + size)[0]
        assert checksum == binascii.crc32(kind + payload) & 0xFFFFFFFF
        result.setdefault(kind, []).append(payload)
        offset += 12 + size
    assert offset == len(data)
    return result


def main() -> None:
    assert GOLDEN == independently_constructed()
    chunks = parse_chunks(GOLDEN)
    assert list(chunks) == [b"IHDR", b"IDAT", b"IEND"]
    assert chunks[b"IHDR"] == [struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)]
    assert chunks[b"IEND"] == [b""]

    stream = b"".join(chunks[b"IDAT"])
    inflater = zlib.decompressobj()
    decoded = inflater.decompress(stream) + inflater.flush()
    assert inflater.eof and not inflater.unused_data and not inflater.unconsumed_tail
    assert decoded == RAW
    print("PNG encoder golden: CRCs and independent zlib decode OK")


if __name__ == "__main__":
    main()
