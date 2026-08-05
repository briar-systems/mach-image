#!/usr/bin/env python3
"""Generate src/pngsuite.mach from an extracted PngSuite corpus.

Usage: gen_pngsuite.py <corpus-dir> [-o src/pngsuite.mach]

<corpus-dir> is the directory of *.png files from PngSuite-2017jul19
(http://www.schaik.com/pngsuite/), unzipped from PngSuite.zip.

For every file, this script independently re-derives (from the PNG spec and,
for the deliberately-corrupt "x*" files, their documented defect) the
DecodeStatus png_info should report -- it does not run the mach decoder and
copy its output. It never calls the mach toolchain.

For files expected to decode successfully, the script also decodes the
expected RGBA8 pixels itself (zlib for inflate, a hand-written unfilter /
Adam7 / palette+tRNS expansion matching the PNG spec) and hashes them with
FNV-1a 64. This is cross-checked against Pillow, an independent decoder, for
every color type, bit depth, and interlace method the corpus contains, before
being trusted -- see verify() below. 16-bit samples are reduced to 8 bits by
keeping the high byte (truncation, matching png.mach's documented rule); no
bKGD background is composited, so alpha is preserved as decoded.
"""

import argparse
import os
import struct
import sys
import zlib

try:
    from PIL import Image
except ImportError:
    Image = None

PNG_SIGNATURE = bytes([137, 80, 78, 71, 13, 10, 26, 10])

COLOR_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}

FNV_OFFSET = 14695981039346656037
FNV_PRIME = 1099511628211
FNV_MASK = (1 << 64) - 1

ADAM7_X_START = [0, 4, 0, 2, 0, 1, 0]
ADAM7_Y_START = [0, 0, 4, 0, 2, 0, 1]
ADAM7_X_STEP = [8, 8, 4, 4, 2, 2, 1]
ADAM7_Y_STEP = [8, 8, 8, 4, 4, 2, 2]


def fnv1a64(data: bytes) -> int:
    """FNV-1a 64-bit, matching dep/mach-std/src/crypto/hash/fnv1a.mach."""
    h = FNV_OFFSET
    for b in data:
        h = ((h ^ b) * FNV_PRIME) & FNV_MASK
    return h


def walk_chunks(data: bytes):
    """(type, payload) for every chunk, assuming data is already well-formed."""
    off = 8
    chunks = []
    while off < len(data):
        dlen = struct.unpack(">I", data[off:off + 4])[0]
        ctype = data[off + 4:off + 8]
        payload = data[off + 8:off + 8 + dlen]
        chunks.append((ctype, payload))
        off += 12 + dlen
        if ctype == b"IEND":
            break
    return chunks


def depth_allowed(color_type: int, depth: int) -> bool:
    if color_type == 0:
        return depth in (1, 2, 4, 8, 16)
    if color_type == 3:
        return depth in (1, 2, 4, 8)
    return depth in (8, 16)


class Verdict:
    """the expected png_info outcome for one file."""

    def __init__(self, status, width=0, height=0, channels=0, hdr=None, plte=None, trns=None):
        self.status = status
        self.width = width
        self.height = height
        self.channels = channels
        self.hdr = hdr
        self.plte = plte
        self.trns = trns


def classify(data: bytes) -> Verdict:
    """re-derive the DecodeStatus png_info should report, from the PNG spec.

    mirrors the chunk-walk a spec-compliant reader performs: signature, then
    every chunk's CRC (a bad CRC anywhere -- not just in IHDR -- fails the
    whole file, since a decoder cannot trust framing past a corrupt chunk),
    then the structural rules (IHDR first, PLTE/tRNS before IDAT, IDAT
    contiguous, IEND terminates the stream, and at least one IDAT). a well-formed file with a
    valid but sub-byte bit depth (1, 2, 4) is DECODE_UNSUPPORTED before any
    later chunk is even inspected -- this decoder's documented scope.
    """
    if len(data) < 8:
        return Verdict("DECODE_TRUNCATED")
    if data[:8] != PNG_SIGNATURE:
        return Verdict("DECODE_BAD_MAGIC")

    off = 8
    seen_ihdr = False
    seen_idat = False
    idat_done = False
    seen_iend = False
    has_plte = False
    plte_entries = 0
    plte_bytes = b""
    has_trns = False
    trns_bytes = b""
    hdr = {}

    while not seen_iend:
        if off + 12 > len(data):
            return Verdict("DECODE_TRUNCATED")
        dlen = struct.unpack(">I", data[off:off + 4])[0]
        if dlen > 0x7FFFFFFF:
            return Verdict("DECODE_BAD_HEADER")
        if off + 12 + dlen > len(data):
            return Verdict("DECODE_TRUNCATED")

        ctype = data[off + 4:off + 8]
        payload = data[off + 8:off + 8 + dlen]
        want = struct.unpack(">I", data[off + 8 + dlen:off + 12 + dlen])[0]
        calc = zlib.crc32(data[off + 4:off + 8 + dlen]) & 0xFFFFFFFF
        if calc != want:
            return Verdict("DECODE_CORRUPT")

        if ctype == b"IHDR":
            if seen_ihdr or off != 8 or dlen != 13:
                return Verdict("DECODE_BAD_HEADER")
            w, h, depth, ct, comp, filt, inter = struct.unpack(">IIBBBBB", payload)
            if w == 0 or h == 0 or w > 0x7FFFFFFF or h > 0x7FFFFFFF:
                return Verdict("DECODE_BAD_HEADER")
            channels = COLOR_CHANNELS.get(ct, 0)
            if channels == 0:
                return Verdict("DECODE_BAD_HEADER")
            if not depth_allowed(ct, depth):
                return Verdict("DECODE_BAD_HEADER")
            if comp != 0 or filt != 0 or inter not in (0, 1):
                return Verdict("DECODE_BAD_HEADER")
            if depth not in (8, 16):
                return Verdict("DECODE_UNSUPPORTED")
            hdr = dict(width=w, height=h, depth=depth, color_type=ct, interlace=inter)
            seen_ihdr = True
        elif not seen_ihdr:
            return Verdict("DECODE_BAD_HEADER")
        elif ctype == b"PLTE":
            if has_plte or has_trns or seen_idat or dlen == 0 or dlen % 3 != 0:
                return Verdict("DECODE_BAD_HEADER")
            if hdr["color_type"] in (0, 4):
                return Verdict("DECODE_BAD_HEADER")
            entries = dlen // 3
            if entries > 256:
                return Verdict("DECODE_BAD_HEADER")
            if hdr["color_type"] == 3 and entries > (1 << hdr["depth"]):
                return Verdict("DECODE_BAD_HEADER")
            has_plte, plte_entries, plte_bytes = True, entries, payload
            idat_done = seen_idat
        elif ctype == b"tRNS":
            if has_trns or seen_idat:
                return Verdict("DECODE_BAD_HEADER")
            ct = hdr["color_type"]
            if ct == 0 and dlen != 2:
                return Verdict("DECODE_BAD_HEADER")
            if ct == 2 and dlen != 6:
                return Verdict("DECODE_BAD_HEADER")
            if ct == 3 and (not has_plte or dlen > plte_entries):
                return Verdict("DECODE_BAD_HEADER")
            if ct not in (0, 2, 3):
                return Verdict("DECODE_BAD_HEADER")
            has_trns, trns_bytes = True, payload
            idat_done = seen_idat
        elif ctype == b"IDAT":
            if idat_done:
                return Verdict("DECODE_BAD_HEADER")
            seen_idat = True
        elif ctype == b"IEND":
            if dlen != 0 or not seen_idat:
                return Verdict("DECODE_BAD_HEADER")
            seen_iend = True
        else:
            if not (ctype[0] & 0x20):
                return Verdict("DECODE_UNSUPPORTED")
            idat_done = seen_idat

        off += 12 + dlen

    if hdr["color_type"] == 3 and not has_plte:
        return Verdict("DECODE_BAD_HEADER")

    channels = 4 if (hdr["color_type"] in (4, 6) or has_trns) else 3
    return Verdict(
        "DECODE_OK", hdr["width"], hdr["height"], channels,
        hdr=hdr, plte=plte_bytes, trns=trns_bytes if has_trns else None,
    )


def pass_extent(size: int, start: int, step: int) -> int:
    if size <= start:
        return 0
    return (size - start + step - 1) // step


def paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def unfilter(ftype: int, cur: bytes, prev, bpp: int) -> bytes:
    out = bytearray(cur)
    n = len(out)
    if ftype == 0:
        pass
    elif ftype == 1:
        for i in range(bpp, n):
            out[i] = (out[i] + out[i - bpp]) & 0xFF
    elif ftype == 2:
        if prev is not None:
            for i in range(n):
                out[i] = (out[i] + prev[i]) & 0xFF
    elif ftype == 3:
        for i in range(n):
            a = out[i - bpp] if i >= bpp else 0
            b = prev[i] if prev is not None else 0
            out[i] = (out[i] + (a + b) // 2) & 0xFF
    elif ftype == 4:
        for i in range(n):
            a = out[i - bpp] if i >= bpp else 0
            b = prev[i] if prev is not None else 0
            c = prev[i - bpp] if (prev is not None and i >= bpp) else 0
            out[i] = (out[i] + paeth(a, b, c)) & 0xFF
    else:
        raise ValueError("undefined filter type %d" % ftype)
    return bytes(out)


def decode_rgba8(data: bytes, hdr: dict, plte: bytes, trns) -> bytes:
    """the RGBA8 raster png_decode is expected to produce for a well-formed file."""
    w, h, depth, ct, inter = hdr["width"], hdr["height"], hdr["depth"], hdr["color_type"], hdr["interlace"]
    channels = COLOR_CHANNELS[ct]
    bpp = channels * (depth // 8)
    idat = b"".join(p for t, p in walk_chunks(data) if t == b"IDAT")
    raw = zlib.decompress(idat)

    out = bytearray(w * h * 4)

    trns_key = None
    if trns is not None:
        mask = (1 << depth) - 1
        if ct == 0:
            trns_key = struct.unpack(">H", trns[0:2])[0] & mask
        elif ct == 2:
            trns_key = tuple(v & mask for v in struct.unpack(">HHH", trns[0:6]))

    def emit(sample: bytes, x: int, y: int):
        base = (y * w + x) * 4
        if ct == 0:
            full = sample[0] if depth == 8 else (sample[0] << 8) | sample[1]
            g = sample[0]
            a = 0 if (trns_key is not None and full == trns_key) else 255
            out[base:base + 4] = bytes((g, g, g, a))
        elif ct == 2:
            if depth == 8:
                r, g, b = sample[0], sample[1], sample[2]
                full = (r, g, b)
            else:
                r, g, b = sample[0], sample[2], sample[4]
                full = (
                    (sample[0] << 8) | sample[1],
                    (sample[2] << 8) | sample[3],
                    (sample[4] << 8) | sample[5],
                )
            a = 0 if (trns_key is not None and full == trns_key) else 255
            out[base:base + 4] = bytes((r, g, b, a))
        elif ct == 3:
            idx = sample[0]
            r, g, b = plte[idx * 3], plte[idx * 3 + 1], plte[idx * 3 + 2]
            a = trns[idx] if (trns is not None and idx < len(trns)) else 255
            out[base:base + 4] = bytes((r, g, b, a))
        elif ct == 4:
            g, a = (sample[0], sample[1]) if depth == 8 else (sample[0], sample[2])
            out[base:base + 4] = bytes((g, g, g, a))
        else:
            if depth == 8:
                r, g, b, a = sample[0], sample[1], sample[2], sample[3]
            else:
                r, g, b, a = sample[0], sample[2], sample[4], sample[6]
            out[base:base + 4] = bytes((r, g, b, a))

    if inter == 0:
        passes = [(0, 0, 1, 1, w, h)]
    else:
        passes = [
            (
                ADAM7_X_START[p], ADAM7_Y_START[p], ADAM7_X_STEP[p], ADAM7_Y_STEP[p],
                pass_extent(w, ADAM7_X_START[p], ADAM7_X_STEP[p]),
                pass_extent(h, ADAM7_Y_START[p], ADAM7_Y_STEP[p]),
            )
            for p in range(7)
        ]

    off = 0
    for x_start, y_start, x_step, y_step, pw, ph in passes:
        if pw == 0 or ph == 0:
            continue
        row_bytes = pw * bpp
        prev = None
        for row in range(ph):
            ftype = raw[off]
            cur = unfilter(ftype, raw[off + 1:off + 1 + row_bytes], prev, bpp)
            y = y_start + row * y_step
            for col in range(pw):
                emit(cur[col * bpp:(col + 1) * bpp], x_start + col * x_step, y)
            prev = cur
            off += 1 + row_bytes

    return bytes(out)


def pil_rgba8(path: str, hdr: dict, trns_key) -> bytes:
    """the same expected raster, decoded independently through Pillow.

    16-bit samples are reduced to 8 bits by hand from full-precision pixel
    data rather than trusting Pillow's own bit-depth conversion: grayscale is
    read through mode 'I' (a full 16-bit int per pixel) and reduced here.
    Pillow has no full-precision 16-bit RGB(A) mode; its PNG decoder already
    keeps only the high byte per sample when loading such an image (verified
    byte-for-byte against a from-scratch scanline defilter before this
    function was trusted), so no further reduction is applied for those.
    """
    im = Image.open(path)
    ct, depth = hdr["color_type"], hdr["depth"]
    w, h = hdr["width"], hdr["height"]
    px = bytearray(w * h * 4)

    if ct == 0:
        im2 = im.convert("I") if depth == 16 else im.convert("L")
        for y in range(h):
            for x in range(w):
                v = im2.getpixel((x, y))
                g = (v >> 8) & 0xFF if depth == 16 else v
                a = 0 if (trns_key is not None and v == trns_key) else 255
                px[(y * w + x) * 4:(y * w + x) * 4 + 4] = bytes((g, g, g, a))
    elif ct == 2:
        im2 = im.convert("RGB")
        key = None
        if trns_key is not None:
            key = tuple((v >> 8) if depth == 16 else v for v in trns_key)
        for y in range(h):
            for x in range(w):
                r, g, b = im2.getpixel((x, y))
                a = 0 if (key is not None and (r, g, b) == key) else 255
                px[(y * w + x) * 4:(y * w + x) * 4 + 4] = bytes((r, g, b, a))
    else:
        im2 = im.convert("RGBA")
        for y in range(h):
            for x in range(w):
                px[(y * w + x) * 4:(y * w + x) * 4 + 4] = bytes(im2.getpixel((x, y)))

    return bytes(px)


def verify(path: str, verdict: Verdict, mine: bytes) -> None:
    """cross-check the from-scratch decode against Pillow; abort on disagreement.

    a mismatch here means the from-scratch decoder (not the mach decoder) has
    a bug -- Pillow is the independent oracle for this step.
    """
    if Image is None:
        sys.exit("PIL/Pillow is required to verify decoded pixels")
    trns_key = None
    if verdict.trns is not None:
        hdr = verdict.hdr
        mask = (1 << hdr["depth"]) - 1
        if hdr["color_type"] == 0:
            trns_key = struct.unpack(">H", verdict.trns[0:2])[0] & mask
        elif hdr["color_type"] == 2:
            trns_key = tuple(v & mask for v in struct.unpack(">HHH", verdict.trns[0:6]))
    ref = pil_rgba8(path, verdict.hdr, trns_key)
    if ref != mine:
        for i in range(0, len(ref), 4):
            if ref[i:i + 4] != mine[i:i + 4]:
                sys.exit(
                    "%s: decode disagrees with PIL at pixel %d: mine=%r pil=%r"
                    % (path, i // 4, mine[i:i + 4], ref[i:i + 4])
                )


CATEGORIES = [
    ("basic", "pngsuite: basic formats"),
    ("interlaced", "pngsuite: interlaced formats"),
    ("filter", "pngsuite: scanline filters"),
    ("odd-size", "pngsuite: odd sizes"),
    ("transparency", "pngsuite: transparency"),
    ("gamma", "pngsuite: gamma"),
    ("order", "pngsuite: chunk order and compression"),
    ("ancillary", "pngsuite: ancillary chunks"),
    ("corrupt", "pngsuite: corrupt files"),
]


def category(stem: str) -> str:
    """which generated test a file's cases belong to, by its PngSuite prefix.

    prefixes follow the naming convention documented on the PngSuite page
    (http://www.schaik.com/pngsuite/pngsuite.html#basic): colortype+bitdepth
    suffix, category-specific prefix, i/n for interlaced/non-interlaced.
    """
    if stem == "PngSuite":
        return "ancillary"          # the suite's own logo image
    if stem.startswith("x"):
        return "corrupt"
    if stem.startswith("basi"):
        return "interlaced"
    if stem.startswith("basn"):
        return "basic"
    if stem[:2] in ("bg", "cd", "ch", "cm", "cs", "ct") or stem.startswith("exif") \
            or stem.startswith("ccw") or stem[:2] in ("pp", "ps"):
        return "ancillary"          # bKGD/pHYs/cHRM/hIST/tIME/tEXt/sBIT/eXIf/PLTE/sPLT
    if stem[:2] in ("f0", "f9"):
        return "filter"
    if stem[:2] in ("s0", "s3", "s4"):
        return "odd-size"
    if stem[:2] in ("tb", "tm", "tp"):
        return "transparency"
    if stem[:1] == "g" and stem[1:2] in ("0", "1", "2"):
        return "gamma"
    if stem.startswith("oi") or stem.startswith("z0"):
        return "order"
    raise ValueError("no category rule for %r" % stem)


def mach_name(filename: str) -> str:
    stem = filename.lower().replace(".", "_").replace("-", "_")
    return stem


def wrap_values(values, width: int = 96, indent: str = "    ") -> str:
    tokens = [str(v) for v in values]
    lines, line = [], indent
    for i, tok in enumerate(tokens):
        piece = tok + ("," if i < len(tokens) - 1 else "")
        sep = "" if line == indent else " "
        if len(line) + len(sep) + len(piece) > width:
            lines.append(line)
            line = indent + piece
        else:
            line += sep + piece
    lines.append(line)
    return "\n".join(lines)


def emit_array(name: str, data: bytes) -> str:
    n = len(data)
    body = wrap_values(list(data))
    return "var %s: [%d]u8 = [%d]u8{\n%s\n};" % (name, n, n, body)


def build(corpus_dir: str) -> str:
    filenames = sorted(f for f in os.listdir(corpus_dir) if f.endswith(".png"))
    entries = []   # (filename, stem, name, data, verdict)
    for filename in filenames:
        path = os.path.join(corpus_dir, filename)
        data = open(path, "rb").read()
        verdict = classify(data)
        entries.append((filename, filename[:-4], mach_name(filename), data, verdict))

    decodable = []   # (name, data, verdict, hash)
    for filename, stem, name, data, verdict in entries:
        if verdict.status != "DECODE_OK":
            continue
        path = os.path.join(corpus_dir, filename)
        pixels = decode_rgba8(data, verdict.hdr, verdict.plte, verdict.trns)
        verify(path, verdict, pixels)
        decodable.append((name, data, verdict, fnv1a64(pixels)))

    buckets = {key: [] for key, _ in CATEGORIES}
    for filename, stem, name, data, verdict in entries:
        buckets[category(stem)].append((filename, stem, name, data, verdict))

    out = []
    out.append(HEADER.strip("\n"))
    out.append("")
    out.append(IMPORTS.strip("\n"))
    out.append("")
    out.append(EXPECT_INFO.strip("\n"))

    for filename, stem, name, data, verdict in entries:
        out.append("")
        out.append(emit_array(name, data))

    for key, title in CATEGORIES:
        cases = buckets[key]
        out.append("")
        out.append('test "%s" {' % title)
        for i, (filename, stem, name, data, verdict) in enumerate(cases, start=1):
            w, h, ch = verdict.width, verdict.height, verdict.channels
            out.append(
                "    if (expect_info(?%s[0], %d, %s, %d, %d, %d) == 0) { ret %d; }"
                % (name, len(data), verdict.status, w, h, ch, i)
            )
        out.append("    ret 0;")
        out.append("}")

    out.append("")
    out.append(
        "# FNV-1a 64 over the expected RGBA8 output of every file above this decoder\n"
        "# is expected to decode successfully, in the same order as pngsuite_decodable."
    )
    out.append(
        "var pngsuite_hashes: [%d]u64 = [%d]u64{\n%s\n};"
        % (len(decodable), len(decodable), wrap_values([h for _, _, _, h in decodable]))
    )

    out.append("")
    out.append(
        "# the pointer, length, and dimensions of the i-th entry backing\n"
        "# pngsuite_hashes, or nil past the end\n"
        "# ---\n"
        "# i:      index into pngsuite_hashes, 0-based\n"
        "# out_len: set to the entry's byte length\n"
        "# out_w:   set to the entry's expected width\n"
        "# out_h:   set to the entry's expected height\n"
        "# ret:     pointer to the entry's encoded bytes, or nil if i is out of range"
    )
    out.append("pub fun pngsuite_decodable(i: usize, out_len: *usize, out_w: *u32, out_h: *u32) *u8 {")
    for i, (name, data, verdict, h) in enumerate(decodable):
        out.append(
            "    if (i == %d) { out_len[0] = %d; out_w[0] = %d; out_h[0] = %d; ret ?%s[0]; }"
            % (i, len(data), verdict.width, verdict.height, name)
        )
    out.append("    out_len[0] = 0;")
    out.append("    ret nil;")
    out.append("}")
    out.append("")
    out.append("pub val PNGSUITE_DECODABLE_COUNT: usize = %d;" % len(decodable))
    out.append("")
    out.append(DECODE_TEST.strip("\n"))
    out.append("")

    return "\n".join(out)


HEADER = '''
# PngSuite-2017jul19 corpus fixtures and decode property tests
#
# generated by tools/gen_pngsuite.py from the extracted PngSuite corpus
# (http://www.schaik.com/pngsuite/, Willem van Schaik). do not hand-edit;
# regenerate with `python3 tools/gen_pngsuite.py <extracted-corpus-dir>`.
#
# expectations are derived from the PNG spec and each file's documented
# defect, never by running the decoder and recording its output: a
# well-formed file with bit depth 1, 2, or 4 is DECODE_UNSUPPORTED (valid PNG
# this decoder deliberately does not unpack); a well-formed file with depth 8
# or 16 is DECODE_OK, with channels 4 when the color type is 4 or 6 or a tRNS
# chunk is present, else 3. the deliberately-corrupt "x*" files are rejected
# per their documented defect: a bad signature byte is DECODE_BAD_MAGIC, a bad
# chunk CRC is DECODE_CORRUPT, and an undefined color type or bit depth, or a
# missing IDAT chunk, is DECODE_BAD_HEADER. two of the corrupt files
# (xcsn0g01, a bad IDAT checksum; xdtn0g01, a missing IDAT chunk) use bit
# depth 1, so png_info rejects them as DECODE_UNSUPPORTED while parsing IHDR,
# before the chunk walk ever reaches the defect their name documents.
#
# pngsuite_hashes is an FNV-1a 64 table (offset basis 14695981039346656037,
# prime 1099511628211, folded one byte at a time -- see
# dep/mach-std/src/crypto/hash/fnv1a.mach) over the expected RGBA8 output of
# every file this decoder is expected to decode successfully. the expected
# pixels are computed independently of this decoder, with Pillow as a
# cross-check oracle; 16-bit samples are reduced to 8 bits by keeping the high
# byte (truncation, matching this decoder's documented rule), computed by
# hand rather than trusted from Pillow's own bit-depth conversion. no bKGD
# background is composited, so alpha is preserved as decoded.
# pngsuite_decodable hands the decode test below the pointer, length, and
# dimensions for the i-th entry.
'''

IMPORTS = '''
use std.types.size.usize;
use image.codec.Image;
use image.codec.DecodeStatus;
use image.codec.DECODE_OK;
use image.codec.DECODE_BAD_MAGIC;
use image.codec.DECODE_BAD_HEADER;
use image.codec.DECODE_UNSUPPORTED;
use image.codec.DECODE_CORRUPT;
use image.png.png_info;
use image.png.png_decode;
use image.png.png_scratch_len;
use image.codec.image_byte_len;
use fnv: std.crypto.hash.fnv1a;
'''

EXPECT_INFO = '''
# 1 when png_info reports want, and on success the expected geometry too
fun expect_info(data: *u8, len: usize, want: DecodeStatus, w: u32, h: u32, ch: u8) u8 {
    var img: Image;
    val st: DecodeStatus = png_info(data, len, ?img);
    if (st != want) { ret 0; }
    if (want != DECODE_OK) { ret 1; }
    if (img.width != w || img.height != h || img.channels != ch) { ret 0; }
    ret 1;
}
'''

DECODE_TEST = '''
# 256x256 RGB8 is the corpus's largest image: 262144 output bytes over a
# 196865-byte raster plus the inflate window.
var suite_pix:     [262144]u8;
var suite_scratch: [262144]u8;

test "pngsuite: every supported image decodes to its expected pixels" {
    var i: usize = 0;
    for (i < PNGSUITE_DECODABLE_COUNT) {
        var len: usize = 0;
        var w:   u32 = 0;
        var h:   u32 = 0;
        val data: *u8 = pngsuite_decodable(i, ?len, ?w, ?h);
        if (data == nil) { ret (i + 1)::i32; }

        val scratch_need: usize = png_scratch_len(data, len);
        if (scratch_need == 0 || scratch_need > 262144) { ret (i + 1)::i32; }

        var img: Image;
        if (png_decode(data, len, ?suite_pix[0], 262144, ?suite_scratch[0], 262144, ?img) != DECODE_OK) {
            ret (i + 1)::i32;
        }
        if (img.width != w || img.height != h) { ret (i + 1)::i32; }

        var hash: u64 = fnv.FNV_INIT;
        var b:    usize = 0;
        val need: usize = image_byte_len(w, h);
        for (b < need) {
            hash = fnv.step_u8(hash, suite_pix[b]);
            b = b + 1;
        }
        if (hash != pngsuite_hashes[i]) { ret (i + 1)::i32; }
        i = i + 1;
    }
    ret 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("corpus_dir", help="directory of PngSuite *.png files")
    parser.add_argument("-o", "--out", default="src/pngsuite.mach", help="output .mach path")
    args = parser.parse_args()

    text = build(args.corpus_dir)
    with open(args.out, "w") as f:
        f.write(text)
    print("wrote %s (%d bytes)" % (args.out, len(text)), file=sys.stderr)


if __name__ == "__main__":
    main()
