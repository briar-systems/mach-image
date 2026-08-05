# mach-image

Pure-mach image decoding and encoding for the engine and its tooling. No C, no
bindings, no system image libraries — just the codecs implemented directly in
Mach. Project id is `image`, so consumers reach everything as `image.*`.

```mach
use image;

fun example() {
    val format: u8 = image.FORMAT_QOI;
    val name: str = image.format_name(format);   # "qoi"
}
```

Consuming projects vendor mach-image as a normal Mach dependency:

```toml
[deps.mach-image]
git = "https://github.com/briar-systems/mach-image"
ref = "branch/main"
```

## Scope

Decode and encode the raster image formats the engine and tooling actually
need. Decoders are the priority; encoding covers the formats used to emit
images from the toolchain (screenshots, generated assets).

## Formats

| Format | Decode | Encode | Notes |
|---|---|---|---|
| QOI | all chunk types | yes | spec-complete, round-trips |
| TGA | truecolor types 2 and 10, 24- and 32-bit | 32-bit uncompressed | color-mapped and grayscale variants are rejected, not decoded |
| PNG | every spec-defined bit depth across all five color types, filters 0-4, Adam7 interlace, tRNS | RGBA8, filter 0, stored DEFLATE | allocation-free deterministic output; 1/2/4-bit samples decode MSB-first; every chunk CRC is validated |
| JPEG | — | — | not started |

A decoder rejects a variant it does not implement rather than producing
approximate pixels, so an unsupported configuration is always a typed
`DecodeStatus` and never silent corruption.

## Goals

- Decoders, in priority order:
  - **QOI** — first: trivial, dependency-free, and a clean end-to-end vertical
    slice for the codec surface.
  - **TGA** — next: uncompressed and RLE variants, still no external
    dependencies.
  - **PNG** — third: every valid bit depth across every color type, backed by
    mach-std's DEFLATE implementation and the PngSuite corpus.
  - **JPEG** — later, once the lossless formats are solid.
- Encoders for at least **QOI** and **PNG**, sized for tooling use
  (screenshots, generated assets) rather than exhaustive option coverage.
- Zero-cost, allocation-explicit codecs: buffers are caller-supplied, following
  the mach-std encoding idiom (`encoded_len`/`decoded_len` sizing, no hidden
  allocation).

## Non-goals

- Exotic or legacy formats (BMP variants beyond need, GIF, TIFF, WebP, ...).
- Color management — ICC profiles, gamut mapping, and CMS pipelines. Pixels are
  handled in their stored color space; conversion is a consumer concern.

## Multiplatform

The codecs are pure algorithms over byte buffers. There is no OS dependency and
no system library to link; the only platform concern is **endianness**, which
the format readers and writers handle explicitly (image formats define their
own byte order regardless of host). mach-image therefore builds for every
target the Mach compiler supports — currently the `x86_64`, `aarch64`, and
`riscv64` instruction sets across the `linux`, `darwin`, `windows`, and
`freestanding` operating-system targets (see `mach info`). The manifest
declares the `x86_64` linux/windows/darwin triples used across the family;
other targets need only a corresponding `[target.*]` entry.

## Architecture

```
src/
  image.mach    library surface: flat public namespace (VERSION, formats, codecs)
  format.mach   format tags (FORMAT_*), format_name, and best-effort detect
  codec.mach    the shared Image type, colorspace hints, size and status helpers
  qoi.mach      QOI decoder and encoder
  tga.mach      TGA truecolor decoder (types 2 and 10) and a minimal encoder
  png.mach      PNG decoder and deterministic allocation-free RGBA8 encoder
  pngsuite.mach the embedded PngSuite corpus and the tests that run it
```

`codec.mach` defines the library's common currency: an `Image` is an RGBA8
pixel buffer (row-major, top-left origin) with its dimensions and source
metadata. Decoders never allocate — callers parse a header with `*_info`, size
storage with `image_byte_len`, and pass the buffer in; a decode returns a
`DecodeStatus` (`DECODE_OK` or a typed error). Untrusted input is bounds-checked
and rejected cleanly, never trusted.

Each codec lands as its own module (`qoi.mach`, `tga.mach`, ...) exposing its
decode/encode entry points and buffer-sizing helpers, re-exported through
`image.mach` so a bare `use image;` reaches the whole API under one namespace.

The PNG writer sizes caller-owned storage with
`png_encode_bound(width, height)` and writes with
`png_encode(img, dst, dst_len)`. It emits one portable subset: RGBA8,
noninterlaced scanlines using filter 0, wrapped in a zlib stream of stored
DEFLATE blocks. This keeps the first encoder allocation-free and dependency-free
at the cost of compression; a future compressor can fit behind the same API.

## Tests

`test` blocks are self-contained and display-free: codec round-trips and
decode/encode against known-good fixtures, run by `mach test .`. The PNG
encoder's deterministic golden is also parsed and decompressed by Python's
maintained zlib through `tools/verify_png_encoder.py`, so encoder correctness is
not established solely by mach-image's decoder. CI fetches the latest released
Mach compiler and runs both checks on every pull request.
