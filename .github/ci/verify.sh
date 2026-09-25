#!/usr/bin/env bash
set -euo pipefail
# the golden is host-independent, so check it once
if [ "$MACH_CI_PRIMARY" = true ]; then
  python3 tools/verify_png_encoder.py
fi
# the selections guard lists every target, so one leg is the whole signal
case "$MACH_CI_LEG" in
  x86_64-linux) bash test/selections/verify.sh "$MACH_COMPILER" ;;
esac
