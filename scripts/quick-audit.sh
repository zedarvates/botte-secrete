#!/bin/bash
# Botte Secrète — Quick Audit Wrapper
# Usage: ./audit.sh /path/to/project

set -euo pipefail

PROJECT="${1:?Usage: audit.sh /path/to/project}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🧦 Botte Secrète Audit — $(date '+%Y-%m-%d %H:%M:%S')"
echo "Project: $PROJECT"
echo ""

# Karpathy review
echo "=== Karpathy Review ==="
if command -v python3 &>/dev/null; then
    python3 "$SCRIPT_DIR/../skills/karpathy-guidelines/scripts/karpathy-review.py" \
        --diff <(cd "$PROJECT" && git diff HEAD~1 2>/dev/null || echo "") 2>/dev/null || \
        echo "  (no changes or script not found)"
else
    echo "  python3 not available"
fi

# Fallow (JS/TS)
echo ""
echo "=== Fallow Analysis ==="
if command -v fallow &>/dev/null; then
    cd "$PROJECT"
    fallow health --score --hotspots 2>/dev/null || echo "  (fallow failed)"
    fallow dead-code --production 2>/dev/null || true
else
    echo "  fallow not installed: cargo install fallow-cli"
fi

# Knowledge Graph
echo ""
echo "=== Knowledge Graph ==="
if [ -f "$PROJECT/.understand-anything/knowledge-graph.json" ]; then
    python3 -c "
import json
with open('$PROJECT/.understand-anything/knowledge-graph.json') as f:
    kg = json.load(f)
print(f'  Nodes: {len(kg.get(\"nodes\", []))}')
print(f'  Edges: {len(kg.get(\"edges\", []))}')
print(f'  Layers: {len(kg.get(\"layers\", []))}')
print(f'  Tour steps: {len(kg.get(\"tour\", []))}')
" 2>/dev/null || echo "  (failed to parse)"
else
    echo "  No knowledge graph found"
fi

echo ""
echo "✅ Audit complete"
