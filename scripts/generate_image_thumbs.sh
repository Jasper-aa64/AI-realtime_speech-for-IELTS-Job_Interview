#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$ROOT_DIR/web/static/assets/writing"
THUMB_ROOT="$ROOT_DIR/web/static/assets/thumbs"
CWEBP_BIN="${CWEBP_BIN:-$(command -v cwebp || true)}"

if [[ -z "$CWEBP_BIN" || ! -x "$CWEBP_BIN" ]]; then
  echo "Error: cwebp not found. Install it with: brew install webp" >&2
  exit 1
fi

if [[ ! -d "$SOURCE_DIR" ]]; then
  echo "Error: writing image source directory not found: $SOURCE_DIR" >&2
  exit 1
fi

generated=0
skipped=0

while IFS= read -r -d '' source_file; do
  rel_path="${source_file#"$ROOT_DIR/web/static/assets/"}"
  out_file="$THUMB_ROOT/$rel_path.webp"
  mkdir -p "$(dirname "$out_file")"
  if [[ -f "$out_file" && "$out_file" -nt "$source_file" ]]; then
    skipped=$((skipped + 1))
    continue
  fi
  "$CWEBP_BIN" -quiet -resize 640 0 -q 78 "$source_file" -o "$out_file"
  generated=$((generated + 1))
done < <(find "$SOURCE_DIR" -type f \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' \) -print0)

thumb_size="0B"
if [[ -d "$THUMB_ROOT" ]]; then
  thumb_size="$(du -sh "$THUMB_ROOT" | awk '{print $1}')"
fi

echo "Writing image thumbnails: generated ${generated}, skipped ${skipped}, total ${thumb_size}"
