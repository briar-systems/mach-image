#!/usr/bin/env bash
set -euo pipefail
# the golden is host-independent, so check it once
if [ "$MACH_CI_PRIMARY" = true ]; then
  python3 tools/verify_png_encoder.py
fi
