#!/bin/bash
# demo-record.sh — Record a Botte Secrète demo as asciicast + GIF
# Usage: ./scripts/demo-record.sh [output_name]
# Requires: asciinema, agg

set -e
NAME="${1:-botte-demo}"
CAST="/tmp/${NAME}.cast"
GIF="docs/${NAME}.gif"

echo "Recording demo to ${CAST}..."
asciinema rec --overwrite "$CAST" \
  -c "python3 -c '
from skills.auto_router.cli import route
from skills.checkup.cli import run_checkup
print(\"=== Botte Secrète v1.4.0 ===\")
print()
print(\"→ auto_router.route(\\\"fix CSS layout bug\\\")\")
print(route(\"fix CSS layout bug\"))
print()
print(\"→ checkup . (compact)\")
run_checkup(\".\")
'"

echo "Converting to GIF..."
agg "$CAST" "$GIF" --last-frame-duration 3

echo "✅ Demo saved: $GIF ($(du -h "$GIF" | cut -f1))"
