#!/bin/bash
# Pre-commit hook for fallow-like
# Install: cp skills/fallow-like/integrations/pre-commit.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit

set -euo pipefail

echo "🔬 Running fallow-like pre-commit checks..."

# Only check if fallow-like is available
if ! python3 -c "import skills.fallow_like" 2>/dev/null; then
    echo "⚠️  fallow-like not installed, skipping"
    exit 0
fi

# Run quick secrets + dead code scan
python3 -m skills.fallow_like.cli analyze . \
    --format json \
    --output /tmp/fallow-precommit.json \
    2>/dev/null || true

# Check for critical findings
if [ -f /tmp/fallow-precommit.json ]; then
    CRITICAL=$(python3 -c "
import json
with open('/tmp/fallow-precommit.json') as f:
    data = json.load(f)
critical = [x for x in data.get('findings', []) if x.get('severity') in ('critical', 'error')]
print(len(critical))
" 2>/dev/null || echo "0")

    if [ "$CRITICAL" -gt 0 ]; then
        echo "❌ $CRITICAL critical/error findings detected!"
        echo "Run 'python -m skills.fallow_like.cli analyze .' for details."
        exit 1
    fi
fi

echo "✅ Pre-commit checks passed"
