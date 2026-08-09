# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
