"""Read-only strict gate for the registered critical rule contract."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from skills.directives_audit.rules import audit_rules

REQUIRED = frozenset(('rsi.observe-only', 'rsi.bounded-truthful-source', 'rsi.no-invented-evidence'))

def main():
    report = audit_rules(ROOT)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    summary = report["summary"]
    try:
        manifest = json.loads((ROOT / ".botte/rules.json").read_text(encoding="utf-8"))
        ids = {rule["id"] for rule in manifest["rules"]}
    except (OSError, ValueError, KeyError, TypeError):
        ids = set()
    clean = (report["schema"] == "botte.rules-audit/v1"
             and report["manifest_present"] is True
             and REQUIRED <= ids and summary["rules"] >= len(REQUIRED)
             and all(summary[key] == 0 for key in
                     ("errors", "warnings", "conflicts", "unenforced", "stale")))
    if not clean:
        print("BLOCKED/DRIFT: missing critical rule or unclean contract", file=sys.stderr)
    return 0 if clean else 1

if __name__ == "__main__":
    raise SystemExit(main())
