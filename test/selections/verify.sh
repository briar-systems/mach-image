#!/usr/bin/env bash
# every test declared under src runs under some `mach test` selection, on every target
#
# mach tests one artifact's closure (mach#3813), so a module no artifact
# reaches has its tests dropped without a word. this fails on any declared test
# that neither `mach test .` nor `mach test . --lib tests` collects.
set -euo pipefail

mach="${1:-mach}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
scratch="$(mktemp -d "${TMPDIR:-/tmp}/mach-image-selections.XXXXXX")"
trap 'rm -rf -- "$scratch"' EXIT

fail() { echo "FAIL: $1" >&2; exit 1; }

cd "$root"
# a test's qualified name is its module path, `#`, and its name: src/png.mach's
# `test foo` is image.png#foo
project="$(sed -n 's/^id *= *"\(.*\)"$/\1/p' mach.toml)"
grep -rE --include='*.mach' '^[[:space:]]*test [A-Za-z_]' src \
    | sed -E "s|^src/(.*)\.mach:[[:space:]]*test ([A-Za-z_][A-Za-z0-9_]*).*|$project.\1#\2|; s|/|.|g" \
    | sort -u > "$scratch/declared.txt"
[ -s "$scratch/declared.txt" ] || fail "found no test declarations under src"

targets="$(sed -n 's/^\[target\.\([^]]*\)\]$/\1/p' mach.toml)"
[ -n "$targets" ] || fail "mach.toml declares no targets"

list() {
    local out="$1"
    shift
    "$mach" test . "$@" --list > "$out" || fail "could not list: mach test . $*"
}

missing=0
for target in $targets; do
    list "$scratch/$target-image.txt" --target "$target"
    list "$scratch/$target-tests.txt" --lib tests --target "$target"
    cat "$scratch/$target-image.txt" "$scratch/$target-tests.txt" | awk '{print $1}' | sort -u > "$scratch/$target-union.txt"
    dropped="$(comm -23 "$scratch/declared.txt" "$scratch/$target-union.txt")"
    printf '%s: image %d, tests %d, both %d of %d declared\n' "$target" \
        "$(wc -l < "$scratch/$target-image.txt")" "$(wc -l < "$scratch/$target-tests.txt")" \
        "$(comm -12 "$scratch/declared.txt" "$scratch/$target-union.txt" | wc -l)" "$(wc -l < "$scratch/declared.txt")"
    if [ -n "$dropped" ]; then
        echo "::error::$target runs no selection that collects these tests; reach their modules from src/lib/tests.mach:"
        while IFS= read -r location; do printf '  %s\n' "$location"; done <<< "$dropped"
        missing=1
    fi
done

[ "$missing" = 0 ] || exit 1
echo "OK: every test declared under src runs under mach test . or mach test . --lib tests, on every target"
