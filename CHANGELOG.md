# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- png: Deterministic, allocation-free RGBA8 encoding with filter-0 scanlines
  and stored DEFLATE blocks.

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
