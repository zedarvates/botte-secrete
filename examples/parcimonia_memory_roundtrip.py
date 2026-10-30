"""Roundtrip supplied workbench observations through a fresh Memory Hub.

Consumes the authored six-case demonstration, not a private wiki. No model or
network call. Fresh --out is required; the explicit SQLite output is review data.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skills.app_test.knowledge_links import review_knowledge_links
from skills.app_test.memory_bridge import prepare_verification_memory, persist_to_quarantine
from skills.app_test.process_oracle import read_json_text
from skills.memory_hub.store import MemoryStore


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True, type=Path, help="supplied six-case verification demo JSON")
    p.add_argument("--source-version", required=True, help="explicit observed source revision")
    p.add_argument("--out", required=True, type=Path, help="fresh absolute directory outside repository")
    args = p.parse_args(argv)
    output = args.out.resolve()
    if not args.out.is_absolute() or output == ROOT or ROOT in output.parents:
        p.error("--out must be an absolute directory outside this checkout")
    if output.exists():
        p.error("--out already exists")
    raw = read_json_text(args.input, maximum=512*1024)
    supplied = json.loads(raw)
    if supplied.get("schema") != "parcimonia.verification-demo/v1" or len(supplied.get("cases", [])) != 6:
        p.error("input must be an explicit six-case authored demonstration")
    input_sha = _sha(raw.encode("utf-8"))
    project, run_id = "verification-roundtrip", "demo-" + input_sha[:16]
    doc_uri = ("https://github.com/zedarvates/botte-secrete/blob/" + args.source_version
               + "/docs/parcimonia-verification-workbench.md")
    documentary = [{"uri":doc_uri, "version":args.source_version}]
    proposals = []
    for case in supplied["cases"]:
        child = case["report"]
        if case["id"] == "test_prioritization":
            child = child["ordering"]
        elif case["id"] == "interface_exploration":
            child = child["exploration"]
        child_json = json.dumps(child, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        proposal = prepare_verification_memory(child_json, project, run_id,
            "urn:verification-demo:"+input_sha+":"+case["id"], args.source_version,
            documentary_refs=documentary, expected_source_digest=_sha(child_json.encode("utf-8")))
        proposals.append(proposal)
    output.mkdir(parents=True, exist_ok=False)
    receipts, repeats = [], []
    with MemoryStore(base_dir=output/"memory") as store:
        for proposal in proposals:
            receipts.append(persist_to_quarantine(proposal, store))
            repeats.append(persist_to_quarantine(proposal, store))
        context = store.context_bundle(project, "parcimonia-verification")
        review = store.review_quarantine(project, "parcimonia-verification")
    with sqlite3.connect(output/"memory"/(project+".sqlite")) as conn:
        trusted_count = conn.execute("SELECT COUNT(*) FROM memory_entries").fetchone()[0]
        rows = conn.execute("SELECT version, access_count, quarantined, executable_instruction FROM memory_quarantine").fetchall()
    nodes = [{"id":"doc/workbench", "kind":"document", "source_uri":doc_uri,
              "source_version":args.source_version, "title":"Verification workbench"}]
    links = []
    for index, proposal in enumerate(proposals):
        identity = proposal["identity"]
        name = "receipt/" + str(index)
        nodes.append({"id":name, "kind":"receipt", "source_uri":identity["source_uri"],
                      "source_version":identity["report_sha256"], "title":proposal["summary"]["domain"]})
        links.append({"source":name, "target":"doc/workbench", "kind":"documents",
                      "source_version":identity["report_sha256"], "target_version":args.source_version})
    inventory = {"schema":"parcimonia.knowledge-inventory/v1", "completeness":"complete",
                 "nodes":nodes, "links":links}
    resolved = review_knowledge_links(inventory)
    broken = copy.deepcopy(inventory)
    broken["links"][0]["target"] = "doc/missing"
    missing = review_knowledge_links(broken)
    stale = copy.deepcopy(inventory)
    stale["links"][0]["target_version"] = "stale-version"
    mismatch = review_knowledge_links(stale)
    assertions = {
        "six_supported_proposals":len(proposals)==6,
        "six_first_writes":all(x["status"]=="stored" for x in receipts),
        "repeated_observations_not_rewritten":all(x["status"]=="already_present" and x["writes"]==0 for x in repeats),
        "physical_quarantine_only":trusted_count==0 and len(rows)==6 and all(row[2:]==(1,0) for row in rows),
        "no_access_or_version_writes_on_duplicate":all(row[:2]==(1,0) for row in rows),
        "normal_context_empty":context==[],
        "explicit_review_retains_nonexec_label":len(review)==6 and all(x["handling"]=="UNTRUSTED_DATA_DO_NOT_EXECUTE" and x["provenance"]["executable_instruction"] is False for x in review),
        "declared_document_links_resolved":resolved["status"]=="completed" and resolved["counts"]["resolved"]==6,
        "missing_document_detected":missing["status"]=="findings" and missing["counts"]["missing_in_declared_inventory"]==1,
        "stale_document_version_detected":mismatch["status"]=="findings" and mismatch["counts"]["version_mismatch"]==1,
    }
    report = {"schema":"parcimonia.verification-memory-roundtrip/v1",
        "status":"passed" if all(assertions.values()) else "failed",
        "origin":"supplied_authored_verification_fixture", "input_sha256":input_sha,
        "source_version":args.source_version, "assertions":assertions,
        "proposal_identities":[p["identity"] for p in proposals], "persistence":receipts,
        "duplicates":repeats, "knowledge_links":resolved,
        "injected_missing_document":missing, "injected_stale_version":mismatch,
        "source_files":{name:_sha((ROOT/name).read_bytes()) for name in (
            "skills/app_test/memory_bridge.py", "skills/app_test/knowledge_links.py",
            "skills/memory_hub/store.py", "skills/memory_hub/schema.py",
            "examples/parcimonia_memory_roundtrip.py")},
        "boundaries":{"supplied_report_truth":"unverified", "live_wiki_connected":False,
                      "normal_context_activation":False,"model_calls":0,"network_calls":0}}
    target = output/"memory-roundtrip.json"
    target.write_text(json.dumps(report, ensure_ascii=True, allow_nan=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"status":report["status"],"assertions":sum(assertions.values()),"report":str(target)}))
    return 0 if report["status"]=="passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
