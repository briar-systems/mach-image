# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Repository scaffold: project manifest, library surface (`image.mach`), and
  format tags (`FORMAT_*`, `format_name`) as the initial codec-independent
  surface. Decoders (QOI, then TGA, then PNG, then JPEG) follow.
