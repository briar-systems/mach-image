# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- manifest: `linux-arm64` and `darwin-aarch64` targets, so the native aarch64 hosts build and test for themselves instead of falling back to linux-x86_64.
- format: `detect` recognizes the JPEG start-of-image marker, so `Format.jpeg`
  is a case detection can produce. JPEG is still not decoded.

### Changed
- build: std moves to 3.2.0 (`tag/v3.2.0`). No source changes were needed, since the codecs use none of the io surface std 3 reworked.
- ci: CI runs the family pipeline (`briar-systems/.github` `mach-lib.yml`) on the pinned, checksum-verified mach seed: debug and release build and test, `mach fmt --check` and an all-targets release build on x86_64-linux for pull requests into dev, plus native aarch64-linux, windows and darwin legs for pull requests into main. A `gate` job is the one required check. The PNG encoder golden check runs as its verify hook.
- build: Moved to Mach 5.0 and std 2.1. The manifest states every profile
  field, marks its defaults, and depends on `[dep.std]` pinned by the committed
  `dep/std` gitlink in place of `mach.lock`.
- codec: `DecodeStatus` and the `DECODE_*` codes are replaced by the
  `DecodeError` tag (`truncated`, `bad_magic`, `bad_header`,
  `short_buffer: usize`, `short_scratch: usize`, `unsupported`, `corrupt`).
  The buffer cases carry the bytes required. `decode_status_name` is now
  `decode_error_name`.
- codec: Encoders report the new `EncodeError` tag (`empty`, `too_large`,
  `channels`, `colorspace`, `short_buffer: usize`) with `encode_error_name`.
- codec: `image_byte_len(w, h) usize` returning 0 is now `opt[usize]`.
- format: The `FORMAT_*` constants are replaced by the `Format` tag.
  `format_name` takes a `Format`, and `detect` returns `opt[Format]`.
- qoi, tga, png: `*_info(src, len, out) DecodeStatus` is now
  `*_info(src, len) res[Image, DecodeError]`, and
  `*_decode(src, len, dst, dst_len, out) DecodeStatus` is now
  `*_decode(src, len, dst, dst_len) res[Image, DecodeError]`. `png_decode`
  keeps its scratch pair before the dropped `out`.
- qoi, tga, png: `png_scratch_len` returns `res[usize, DecodeError]`,
  `*_encode_bound` returns `res[usize, EncodeError]`, and `*_encode` returns
  `res[usize, EncodeError]` in place of a 0 sentinel.
- qoi, tga, png: Nil buffer and image arguments are caller contract violations
  under std's raw-memory rules instead of reported outcomes.

### Fixed
- image: `VERSION` reported 0.2.0 on the 0.3.0 release.

## [0.3.0] - 2026-08-09

### Added
- png: A PNG decoder. Chunk framing with the ordering and type rules enforced,
  scanline defiltering, Adam7 interlace, sub-byte sample depths, transparency
  keys including the narrow-key masking RGB needs, and IDAT inflated through
  `std.compress.zlib`. Checked against the PngSuite corpus plus property tests
  for the cases a corpus cannot reach.
- png: Deterministic, allocation-free RGBA8 encoding with filter-0 scanlines
  and stored DEFLATE blocks.
- codec: `DECODE_CORRUPT`, so an integrity failure is distinguishable from an
  unsupported format. A decoder that answers "no" the same way for both leaves
  a caller unable to tell a broken file from one it never handled.
- format: PNG is detected by signature, and the format matrix is documented.

### Changed
- manifest: Re-touched to RFC-exact totality per mach#1964/mach#1979.

## [0.2.0] - 2026-07-07

Overhauls the build manifest to comply with the v2 build system schema.

### Changed
- manifest: Migrated manifest to v2 schema (`[artifact.image]`).
- deps: Renamed the `mach-std` dependency section from `[deps.X]` to `[dep.X]`.

## [0.1.0] - 2025-11-15

### Added
- Initial release of mach-image.
