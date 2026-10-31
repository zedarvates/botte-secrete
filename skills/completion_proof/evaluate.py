"""Deterministic synthetic evaluation. Does not execute any model or test payload."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import tempfile

from skills.completion_proof.verify import verify_report

HERE = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")


def build_case(case_id, root):
    """Materialize a curated fixture; ground-truth labels live outside this function."""
    code = b"VALUE = 42\n"
    log = b"Synthetic evaluation fixture: one passing test is declared.\n"
    filename = "calcul_é.py" if case_id == "unicode_source" else "app.py"
    files = {filename: code, "log.txt": log}
    receipt = {"schema_version": 1, "run_id": "evaluation-run",
               "result": {"exit_code": 0, "tests_run": 1, "failures": 0, "errors": 0, "skipped": 0},
               "log": {"path": "log.txt", "sha256": sha(log)},
               "sources": [{"path": filename, "sha256": sha(code)}]}
    report = {"status": "complete", "run_id": "evaluation-run", "proof": {"receipt_ref": "receipt.json"}}
    if case_id in {"legacy_valid", "skips_omitted"}:
        del receipt["result"]["skipped"]
    elif case_id == "mixed_skipped":
        receipt["result"].update(tests_run=2, skipped=1)
    elif case_id == "two_sources":
        files["helper.py"] = b"OTHER = 1\n"
        receipt["sources"].append({"path": "helper.py", "sha256": sha(files["helper.py"])})
    elif case_id == "wrong_run":
        report["run_id"] = "other-run"
    elif case_id == "all_skipped":
        receipt["result"]["skipped"] = 1
    elif case_id == "failed_test":
        receipt["result"].update(exit_code=1, failures=1)
    elif case_id == "bad_counts":
        receipt["result"]["skipped"] = 2
    elif case_id == "traversal":
        receipt["log"]["path"] = "../outside.txt"
    elif case_id == "zero_tests":
        receipt["result"]["tests_run"] = 0
    elif case_id not in {"valid", "unicode_source", "missing_receipt", "missing_log", "missing_source",
                         "receipt_tampered", "log_tampered", "source_changed", "unlisted_change", "dishonest_executor"}:
        raise ValueError("Unknown fixture mutation: " + case_id)
    files["receipt.json"] = encode(receipt)
    pin = sha(files["receipt.json"])
    files["report.json"] = encode(report)
    if case_id == "missing_receipt":
        del files["receipt.json"]
    elif case_id == "missing_log":
        del files["log.txt"]
    elif case_id == "missing_source":
        del files[filename]
    elif case_id == "receipt_tampered":
        files["receipt.json"] += b" "
    elif case_id == "log_tampered":
        files["log.txt"] += b"modified"
    elif case_id == "source_changed":
        files[filename] = b"VALUE = 43\n"
    elif case_id == "unlisted_change":
        files["unlisted_dependency.py"] = b"# scenario: dependency modified after the test\n"
    for name, data in files.items():
        (root / name).write_bytes(data)
    return pin, {name: data.decode("utf-8") for name, data in files.items()}


def metrics(rows):
    """Positive = unsafe completion; detection = verifier rejects it."""
    counts = {"true_positive": 0, "false_positive": 0, "false_negative": 0, "true_negative": 0}
    for row in rows:
        unsafe = not row["safe_to_accept"]
        detected = not row["observed_verified"]
        key = ("true_positive" if detected else "false_negative") if unsafe else (
            "false_positive" if detected else "true_negative")
        counts[key] += 1
    tp, fp, fn, tn = (counts[key] for key in ("true_positive", "false_positive", "false_negative", "true_negative"))
    counts.update(cases=len(rows), false_alert_rate=fp / (fp + tn) if fp + tn else None,
                  miss_rate=fn / (fn + tp) if fn + tp else None,
                  precision=tp / (tp + fp) if tp + fp else None,
                  recall=tp / (tp + fn) if tp + fn else None)
    return counts


def evaluate():
    corpus = json.loads((HERE / "evaluation_cases.json").read_text(encoding="utf-8"))
    cases = corpus["cases"]
    seen = set()
    rows = []
    for case in cases:
        if (case["id"] in seen or type(case["safe_to_accept"]) is not bool
                or case["group"] not in {"contract", "limits"} or not case["reason"]):
            raise ValueError("Invalid evaluation label")
        seen.add(case["id"])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pin, inputs = build_case(case["id"], root)
            result = verify_report(root / "report.json", evidence_root=root, source_root=root,
                                   trusted_receipt_sha256=pin)
        rows.append(dict(case, observed_verified=result["verified"], result=result,
                         trusted_receipt_sha256=pin, input_files=inputs))
    groups = {group: metrics([row for row in rows if row["group"] == group])
              for group in ("contract", "limits")}
    return {"schema_version": 1, "corpus_type": "curated synthetic; not held out",
            "positive_definition": "completion not justified by the scenario ground truth",
            "groups": groups, "overall": metrics(rows), "cases": rows,
            "source_sha256": {name: sha((HERE / name).read_bytes()) for name in
                              ("verify.py", "evaluate.py", "evaluation_cases.json")}}


def markdown(result):
    lines = ["# Mesure de fiabilité — corpus synthétique", "",
             "20 scénarios préparés et étiquetés, pas un échantillon de production ni un test indépendant.", "",
             "Une détection signifie que Botte refuse une clôture injustifiée. Une fausse alerte est un cas valable refusé ; un problème manqué est un cas injustifié accepté.", "",
             "| Groupe | Cas | Problèmes détectés | Fausses alertes | Problèmes manqués | Cas valables acceptés |",
             "|---|---:|---:|---:|---:|---:|"]
    for label, group in (("Contrat couvert", "contract"), ("Limites connues", "limits")):
        m = result["groups"][group]
        lines.append(f"| {label} | {m['cases']} | {m['true_positive']} | {m['false_positive']} | {m['false_negative']} | {m['true_negative']} |")
    lines += ["", "## Résultats cas par cas", "", "| Cas | Groupe | Attendu | Observé |", "|---|---|---|---|"]
    for row in result["cases"]:
        lines.append(f"| {row['id']} | {row['group']} | {'Accepter' if row['safe_to_accept'] else 'Refuser'} | {'Accepté' if row['observed_verified'] else 'Refusé'} |")
    lines += ["", "## Interprétation", "",
              "Les limites sont volontairement conservées dans le bilan : tests ignorés non déclarés, dépendance modifiée hors des fichiers listés, exécuteur malhonnête fournissant aussi la référence de confiance.", "",
              "Un bon résultat sur les cas couverts ne prouve pas une fiabilité générale. Le corpus a été conçu en connaissant le code ; il est petit, non indépendant et sans fréquence représentative des usages réels. Les trois cas de limites violent ou dépassent les hypothèses du vérificateur, mais restent des clôtures injustifiées selon le scénario.", "",
              "Aucun vrai test applicatif ni modèle n'est lancé par cet évaluateur : les reçus et journaux sont des fixtures synthétiques. Les exécutions réelles sont documentées séparément dans la démonstration du correctif.", "",
              "[Données, labels, entrées et résultats complets](results.json). Les empreintes dans ce fichier identifient le code et le corpus utilisés."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE.parents[1] / ".botte-cache/completion-evaluation")
    args = parser.parse_args()
    result = evaluate()
    output = args.output.resolve() / datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True)
    (output / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "README.md").write_text(markdown(result), encoding="utf-8")
    print(json.dumps({"output": str(output), "groups": result["groups"], "overall": result["overall"]}))


if __name__ == "__main__":
    main()
