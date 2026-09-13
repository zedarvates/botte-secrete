"""Replay a real verifier bug: a fully skipped unittest run was accepted.

Uses a fixed Git revision as the unmodified before implementation, not a
hand-written faulty stand-in. No network, model, or repository mutation.
"""
import argparse
import datetime
import hashlib
import io
import json
import subprocess
import sys
import types
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BASELINE = "4cffa4b941979ef84518b12c2b5d139fb07a8550"
SOURCE = "skills/completion_proof/verify.py"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPO / ".botte-cache/real-completion-fix")
    args = parser.parse_args()
    old = subprocess.run(["git", "show", BASELINE + ":" + SOURCE], cwd=REPO,
                         capture_output=True, timeout=30)
    if old.returncode:
        parser.error("Baseline commit unavailable. Use a Git checkout containing " + BASELINE)
    run = args.output.resolve() / datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run.mkdir(parents=True)

    def save(name, value):
        (run / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    (run / "before-verifier.py").write_bytes(old.stdout)
    (run / "after-verifier.py").write_bytes((REPO / SOURCE).read_bytes())
    test_code = '''import unittest

class OptionalTest(unittest.TestCase):
    @unittest.skip("optional backend unavailable")
    def test_optional_backend(self):
        self.fail("A skipped test must never reach this body")
'''
    (run / "test_optional.py").write_text(test_code, encoding="utf-8")
    source_hash = digest(run / "test_optional.py")
    module = types.ModuleType("demo_optional")
    exec(compile(test_code, "test_optional.py", "exec"), module.__dict__)
    log = io.StringIO()
    actual = unittest.TextTestRunner(stream=log, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(module))
    if not (actual.wasSuccessful() and actual.testsRun == 1 and len(actual.skipped) == 1):
        raise RuntimeError("The actual skipped-test reproduction changed")
    if digest(run / "test_optional.py") != source_hash:
        raise RuntimeError("Test source changed during execution")
    (run / "test-output.txt").write_text(log.getvalue(), encoding="utf-8")
    receipt = {"schema_version": 1, "run_id": run.name,
               "result": {"exit_code": 0 if actual.wasSuccessful() else 1,
                          "tests_run": actual.testsRun, "failures": len(actual.failures),
                          "errors": len(actual.errors), "skipped": len(actual.skipped)},
               "log": {"path": "test-output.txt", "sha256": digest(run / "test-output.txt")},
               "sources": [{"path": "test_optional.py", "sha256": source_hash}]}
    save("receipt.json", receipt)
    pin = digest(run / "receipt.json")
    (run / "trusted-receipt.sha256").write_text(pin + "\n", encoding="utf-8")
    save("report.json", {"status": "complete", "run_id": run.name,
                         "proof": {"receipt_ref": "receipt.json"}})
    outcomes = {}
    for phase in ("before", "after"):
        implementation = types.ModuleType("verifier_" + phase)
        data = (run / (phase + "-verifier.py")).read_bytes()
        exec(compile(data, phase + "-verifier.py", "exec"), implementation.__dict__)
        value = implementation.verify_report(run / "report.json", evidence_root=run,
                    source_root=run, trusted_receipt_sha256=pin)
        save(phase + "-result.json", value)

        class Regression(unittest.TestCase):
            def test_skipped_run_must_not_verify(self):
                self.assertFalse(value["verified"], "All tests were skipped, yet receipt was verified")

        regression_log = io.StringIO()
        regression = unittest.TextTestRunner(stream=regression_log).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(Regression))
        text = regression_log.getvalue().replace(str(Path(__file__).resolve()), "real_fix.py")
        (run / (phase + "-regression.txt")).write_text(text, encoding="utf-8")
        outcomes[phase] = {"verified": value["verified"],
                           "regression_passed": regression.wasSuccessful(),
                           "implementation_sha256": hashlib.sha256(data).hexdigest()}
    if not (outcomes["before"]["verified"] and not outcomes["before"]["regression_passed"]
            and not outcomes["after"]["verified"] and outcomes["after"]["regression_passed"]):
        raise RuntimeError("Before/after regression expectation not met")
    save("summary.json", {"baseline_git_commit": BASELINE, "source": SOURCE,
                           "actual_tests_discovered": 1, "actual_tests_skipped": 1,
                           "actual_tests_executed": 0, "results": outcomes,
                           "limits": "One actual verifier regression; trusted executor; not an autonomous agent run."})
    save("sha256.json", {p.name: digest(p) for p in sorted(run.iterdir()) if p.is_file()})
    page = '''<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Botte : un vrai correctif</title><style>body{background:#f4f1e9;color:#202d2a;font:18px/1.65 system-ui;margin:0}main{max-width:950px;margin:auto;padding:42px 24px}h1{font-size:clamp(32px,5vw,52px);line-height:1.15}h2{font-size:24px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}article{background:#fffdf8;border:1px solid #d8dacf;border-radius:14px;padding:25px}a{color:#245840}aside{border-left:5px solid #b5722c;padding:10px 22px;margin:30px 0}small{color:#58685d}@media(max-width:650px){.grid{grid-template-columns:1fr}}</style><main><small>BOTTE SECRÈTE · CORRECTIF RÉEL ET REPRODUCTIBLE</small><h1>Un test ignoré<br>n'est pas un test réussi.</h1><p>Un vrai lancement de unittest découvre un test, l'ignore et termine sans erreur. L'ancien vérificateur de Botte validait son reçu malgré l'absence de test exécuté.</p><div class="grid"><article><h2>Avant : une validation injustifiée</h2><p>Ancienne version extraite du commit public <code>4cffa4b</code>. Le reçu déclare explicitement un test ignoré.</p><p><strong>Botte : vérifié = vrai.</strong><br>Le test de non-régression échoue.</p><a href="RUN/before-result.json">Résultat de Botte</a> · <a href="RUN/before-regression.txt">Échec du contrôle</a></article><article><h2>Après : le reçu est refusé</h2><p>Le correctif contrôle le nombre de tests ignorés. Si tous ont été ignorés, le reçu ne permet pas une validation.</p><p><strong>Botte : vérifié = faux.</strong><br>Le même test de non-régression réussit.</p><a href="RUN/after-result.json">Résultat corrigé</a> · <a href="RUN/after-regression.txt">Réussite du contrôle</a></article></div><h2>Les pièces de l'exécution</h2><p><a href="RUN/test-output.txt">Test réellement ignoré</a> · <a href="RUN/receipt.json">Même reçu pour les deux versions</a> · <a href="RUN/before-verifier.py">Code avant</a> · <a href="RUN/after-verifier.py">Code après</a> · <a href="RUN/summary.json">Provenance</a> · <a href="RUN/sha256.json">Empreintes</a></p><aside>Ce défaut a été découvert dans le nouveau vérificateur de notre proposition GitHub. Ce n'est pas un incident de production ni une correction réalisée par un agent autonome. Le contrôle dépend toujours d'un exécuteur de confiance : les anciens reçus qui omettent le nombre de tests ignorés restent une limite de compatibilité.</aside><p>Pour rejouer depuis un clone contenant le commit de référence :</p><pre>python docs/demos/completion-proof/real_fix.py</pre><small>Résultats enregistrés, aucune exécution déclenchée par l'ouverture de cette page.</small></main></html>'''
    (run.parent / "real-fix.html").write_text(page.replace("RUN", run.name), encoding="utf-8")
    print(json.dumps({"run": str(run), "before_regression": "failed", "after_regression": "passed"}))


if __name__ == "__main__":
    main()
