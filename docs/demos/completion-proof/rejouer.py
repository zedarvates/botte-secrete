"""Demonstration locale. Usage: python docs/demos/completion-proof/rejouer.py"""
from pathlib import Path
import argparse
import datetime
import hashlib
import html
import json
import os
import subprocess
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parents[2]

def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

def save(path, obj):
    write(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--botte", type=Path, default=REPO)
    parser.add_argument("--output", type=Path, default=REPO / ".botte-cache/completion-proof-demo")
    args = parser.parse_args()
    repo = args.botte.resolve()
    BASE = args.output.resolve()
    if not (repo / "skills/completion_proof/cli.py").is_file():
        parser.error("Module completion_proof introuvable dans ce depot.")
    run = BASE / "executions" / datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run.mkdir(parents=True)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(repo))

    def execute(argv, cwd, log):
        result = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", timeout=60)
        public_log = result.stdout + result.stderr
        for prefix in (str(run), run.as_posix(), str(repo), repo.as_posix()):
            public_log = public_log.replace(prefix, "<local-root>")
        write(run / log, public_log)
        return result

    def audit(report, name):
        result = execute([sys.executable, "-m", "skills.completion_proof.cli", report.relative_to(run).as_posix(), "--json"], run, name)
        if result.returncode:
            raise RuntimeError("Echec du detecteur: " + result.stderr)
        data = json.loads(result.stdout)
        if data.get("error") or data.get("errors") or data.get("files_scanned") != 1:
            raise RuntimeError("Analyse incomplete")
        return data

    tests = '''import unittest
from moyenne import moyenne

class TestMoyenne(unittest.TestCase):
    def test_valeurs_positives(self):
        self.assertEqual(moyenne([2, 4, 6]), 4)
    def test_valeurs_negatives(self):
        self.assertEqual(moyenne([-2, -4]), -3)
    def test_liste_vide(self):
        self.assertEqual(moyenne([]), 0)

if __name__ == "__main__":
    unittest.main(verbosity=2)
'''
    before = run / "avant"
    after = run / "apres"
    write(before / "moyenne.py", "def moyenne(valeurs):\n    return sum(valeurs) / len(valeurs)\n")
    write(after / "moyenne.py", "def moyenne(valeurs):\n    if not valeurs:\n        return 0\n    return sum(valeurs) / len(valeurs)\n")
    for folder in (before, after):
        write(folder / "test_moyenne.py", tests)
    save(before / "rapport-agent.json", {"status": "complete", "message": "La fonction moyenne est terminee.", "scenario": "Declaration mise en scene pour la demonstration; aucun agent autonome execute."})
    initial = audit(before / "rapport-agent.json", "01-audit-avant.json")
    snapshots = {folder.name: {name: digest(folder / name)
                             for name in ("moyenne.py", "test_moyenne.py")}
                 for folder in (before, after)}
    failed = execute([sys.executable, "-m", "unittest", "-v", "test_moyenne"], before, "02-tests-avant.txt")
    passed = execute([sys.executable, "-m", "unittest", "-v", "test_moyenne"], after, "03-tests-apres.txt")
    if any(digest(folder / name) != value for folder in (before, after)
           for name, value in snapshots[folder.name].items()):
        raise RuntimeError("Source ou tests modifies pendant l'execution")
    if initial["summary"]["total"] != 1 or failed.returncode == 0 or passed.returncode != 0:
        raise RuntimeError("Le scenario ne produit pas les resultats attendus.")
    if "Ran 3 tests" not in passed.stderr or "OK" not in passed.stderr:
        raise RuntimeError("Execution des trois tests non confirmee.")
    save(after / "rapport-agent.json", {"status": "complete", "message": "Moyenne corrigee pour la liste vide (convention du scenario: resultat 0).", "proof": {"cmd_output_ref": "../03-tests-apres.txt", "artifact_hash": digest(after / "moyenne.py")}, "validations": [{"name": "unittest: 3 cas", "status": "passed", "reference": "../03-tests-apres.txt"}]})
    final = audit(after / "rapport-agent.json", "04-audit-apres.json")
    # Controle negatif: ne pas confondre reference presente et preuve authentifiee.
    save(run / "controle-limite.json", {"status": "complete", "proof": {"cmd_output_ref": "preuve-inexistante.txt"}})
    limitation = audit(run / "controle-limite.json", "05-audit-limite.json")
    if final["summary"]["total"] != 0 or limitation["summary"]["total"] != 0:
        raise RuntimeError("Comportement du detecteur different: presentation a reviser.")
    module_tests = execute([sys.executable, "-m", "skills.completion_proof.test_completion_proof"], repo, "06-tests-detecteur.txt")
    if module_tests.returncode != 0:
        raise RuntimeError("Les tests du detecteur echouent.")
    # This demo executor captures the trusted digest outside the agent report.
    # It is a local integrity anchor, not an independently signed attestation.
    def verify(claim, source_dir, pin, output):
        result = execute([sys.executable, "-m", "skills.completion_proof.cli",
                          claim, "--verify", "--json", "--evidence-root", ".",
                          "--source-root", source_dir, "--receipt-sha256", pin],
                         run, output)
        if result.returncode:
            raise RuntimeError("Verification non executee")
        return json.loads(result.stdout)

    checks = {}
    for folder, outcome, log in ((before, failed, "02-tests-avant.txt"),
                                 (after, passed, "03-tests-apres.txt")):
        run_id = run.name + "-" + folder.name
        receipt_name = folder.name + "-receipt.json"
        claim_name = folder.name + "-claim-v1.json"
        save(run / receipt_name, {
            "schema_version": 1, "run_id": run_id,
            "result": {"exit_code": outcome.returncode, "tests_run": 3,
                       "failures": 0, "errors": 1 if folder == before else 0},
            "log": {"path": log, "sha256": digest(run / log)},
            "sources": [{"path": name, "sha256": value}
                        for name, value in snapshots[folder.name].items()],
        })
        pin = digest(run / receipt_name)
        write(run / (folder.name + "-trusted-receipt.sha256"), pin + "\n")
        save(run / claim_name, {"status": "complete", "run_id": run_id,
                               "proof": {"receipt_ref": receipt_name}})
        checks[folder.name] = verify(claim_name, folder.name, pin,
                                     folder.name + "-verification.json")
    checks["source_changed"] = verify("apres-claim-v1.json", "avant", pin,
                                       "source-changed-verification.json")
    checks["missing"] = verify("controle-limite.json", "apres", pin,
                                "missing-verification.json")
    if (checks["avant"]["status"] != "test_failed"
            or not checks["apres"]["verified"]
            or checks["source_changed"]["verified"]
            or checks["missing"]["status"] != "missing_evidence"):
        raise RuntimeError("Verification des preuves inattendue")
    save(run / "verification-summary.json", checks)
    strict_checks = {}
    human_results = []
    for label, claim, source_dir, expected in (
        ("valid", "apres-claim-v1.json", "apres", 0),
        ("missing", "controle-limite.json", "apres", 3),
        ("wrong_version", "apres-claim-v1.json", "avant", 4),
        ("failed_tests", "avant-claim-v1.json", "avant", 5),
    ):
        expected_pin = (run / ("avant-trusted-receipt.sha256" if label == "failed_tests"
                               else "apres-trusted-receipt.sha256")).read_text(encoding="utf-8").strip()
        strict = execute([sys.executable, "-m", "skills.completion_proof.cli", claim,
                          "--verify", "--strict", "--json", "--evidence-root", ".",
                          "--source-root", source_dir, "--receipt-sha256", expected_pin],
                         run, "strict-" + label + ".json")
        if strict.returncode != expected:
            raise RuntimeError("Code de sortie strict inattendu")
        marker = run / ("closed-" + label + ".txt")
        if strict.returncode == 0:
            write(marker, "Closure allowed after strict verification.\n")
        strict_checks[label] = {"exit_code": strict.returncode,
                                "closure_marker_written": marker.exists()}
        human = execute([sys.executable, "-m", "skills.completion_proof.cli", claim,
                         "--verify", "--strict", "--lang", "fr", "--evidence-root", ".",
                         "--source-root", source_dir, "--receipt-sha256", expected_pin],
                        run, "human-" + label + ".txt")
        if human.returncode != expected:
            raise RuntimeError("La langue a modifie le resultat strict")
        human_results.append((label, human.stdout))
    save(run / "strict-summary.json", strict_checks)
    sources = {}
    for name in ("__init__.py", "audit.py", "cli.py", "test_completion_proof.py", "verify.py", "test_verify.py", "presentation.py"):
        path = repo / "skills/completion_proof" / name
        sources["skills/completion_proof/" + name] = digest(path)
    proof_log = (after / "../03-tests-apres.txt").resolve()
    if not proof_log.is_file():
        raise RuntimeError("La preuve citee est absente")
    save(run / "resultats.json", {"scenario": "synthetique, executions reelles", "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "before_findings": initial["summary"]["total"], "before_tests_exit_code": failed.returncode, "after_findings": final["summary"]["total"], "after_tests_exit_code": passed.returncode, "tests_count": 3, "missing_reference_findings": limitation["summary"]["total"], "detector_tests_exit_code": module_tests.returncode, "detector_source_sha256": sources, "limits": ["A11 est un detecteur declaratif, pas un validateur de la veracite des preuves.", "Le CLI A11 retourne zero meme en presence de constats.", "La correction et le controle des preuves sont orchestres par ce script de demonstration.", "Trois cas de test ne prouvent pas une correction universelle."]})
    manifest = {str(p.relative_to(run)).replace("\\", "/"): digest(p) for p in sorted(run.rglob("*")) if p.is_file()}
    save(run / "empreintes.json", manifest)
    rel = run.relative_to(BASE).as_posix()
    page = '''<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Botte Secrète — de l'annonce à la preuve</title>
<style>*{box-sizing:border-box}body{margin:0;background:#f4f1e9;color:#202d2a;font:18px/1.6 system-ui,sans-serif}main{max-width:1000px;margin:auto;padding:55px 24px}small,.eyebrow{letter-spacing:.12em;text-transform:uppercase;font-size:12px;font-weight:750;color:#416653}h1{font-size:clamp(34px,6vw,62px);line-height:1.08;max-width:800px;margin:18px 0}h2{font-size:24px;margin:0 0 12px}.intro{max-width:760px;color:#4c5953}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin:32px 0}.card{background:#fffdf8;border:1px solid #d8dacf;border-radius:15px;padding:25px}.n{font-size:13px;font-weight:800;color:#576a59}.badge{display:inline-block;padding:3px 10px;border-radius:7px;background:#fae5cd;color:#79401b;font-size:14px;font-weight:700}.green{background:#dceedd;color:#235230}a{color:#245840;text-underline-offset:4px}pre{overflow:auto;font-size:13px;background:#eeeee6;padding:16px;border-radius:8px;white-space:pre-wrap}button{font:inherit;background:#234b39;color:white;border:0;border-radius:9px;padding:12px 20px;cursor:pointer}button:focus-visible,a:focus-visible{outline:3px solid #ce7e25;outline-offset:4px}.limit{border-left:5px solid #bb762f;padding:12px 22px;background:#efe5d4}footer{font-size:14px;color:#5a645e;margin-top:25px}@media(max-width:650px){.grid{grid-template-columns:1fr}main{padding-top:28px}}</style>
<main><div class="eyebrow">Botte Secrète / démonstration locale</div><h1>« Terminé » mérite<br>une preuve.</h1><p class="intro">Un rapport annonce une fonction terminée. Botte Secrète repère l'absence de preuve. Un vrai test révèle ensuite un défaut ; une correction permet aux trois tests de réussir.</p><p><small>Scénario préparé · contrôles réellement exécutés</small></p>
<button id="play" type="button">Découvrir le parcours</button><p id="status" aria-live="polite">Les quatre étapes sont visibles ci-dessous.</p>
<div class="grid">
<section class="card"><div class="n">01 / L'ANNONCE</div><h2>L'agent dit « terminé ».</h2><p>La fonction calcule une moyenne. Son rapport ne cite aucun test ni résultat vérifiable.</p><pre>{"status": "complete"}</pre><a href="RUN/avant/rapport-agent.json">Lire le rapport préparé</a></section>
<section class="card"><div class="n">02 / LE CONTRÔLE</div><h2>Botte repère le manque.</h2><span class="badge">1 déclaration sans preuve</span><p>Le détecteur A11 signale le rapport. Il n'exécute pas les tests et ne bloque pas automatiquement le travail.</p><a href="RUN/01-audit-avant.json">Voir le résultat réel de Botte</a></section>
<section class="card"><div class="n">03 / LA CORRECTION</div><h2>Le test révèle un défaut.</h2><p>Une liste vide provoque une division par zéro. La convention de cet exemple prévoit un résultat de zéro : nous ajoutons ce cas à la fonction.</p><span class="badge">Avant : 3 tests, 1 erreur</span><p><a href="RUN/02-tests-avant.txt">Lire l'échec réel</a> · <a href="RUN/apres/moyenne.py">Voir la correction</a></p></section>
<section class="card"><div class="n">04 / LA PREUVE</div><h2>Le résultat devient contrôlable.</h2><span class="badge green">Après : 3 tests réussis</span><p>Le rapport cite la sortie réelle et l'empreinte du code corrigé. Botte ne relève plus d'absence de preuve.</p><a href="RUN/03-tests-apres.txt">Lire les tests réussis</a> · <a href="RUN/04-audit-apres.json">Voir le nouvel audit</a></section>
</div><aside class="limit"><h2>Ce que cette démonstration prouve</h2><p>Botte détecte ici une annonce sans preuve associée. Les tests exécutés séparément établissent la correction sur trois cas précis.</p><p><strong>Une référence présente n'est pas une preuve authentifiée.</strong> Un contrôle supplémentaire montre qu'A11 accepte aussi une référence fictive. Ce détecteur seul ne garantit donc ni la vérité du rapport, ni l'absence de bugs.</p><a href="RUN/05-audit-limite.json">Consulter ce contrôle de limite</a></aside>
<details><summary>Consulter les pièces et rejouer</summary><p><a href="RUN/resultats.json">Résultats de l'exécution</a> · <a href="RUN/empreintes.json">Empreintes SHA-256</a> · <a href="RUN/06-tests-detecteur.txt">Tests du détecteur</a> · <a href="README.md">Mode d'emploi</a></p><p>Le bouton raconte l'exécution enregistrée. Pour relancer réellement les contrôles, utiliser le script fourni avec une installation locale de Botte Secrète.</p></details><footer>Aucun appel à un modèle dans le scénario. L'annonce et la correction sont préparées ; les audits et tests sont exécutés. Aucun dépôt n'est publié. Exécution : RUN.</footer></main>
<script>const cards=[...document.querySelectorAll('.card')];let step=-1;document.querySelector('#play').addEventListener('click',()=>{step=(step+1)%4;cards.forEach((c,i)=>c.style.outline=i===step?'3px solid #507452':'none');document.querySelector('#status').textContent=['1 / Une annonce de réalisation, sans preuve jointe.','2 / Botte détecte exactement une déclaration sans preuve.','3 / Le test échoue sur la liste vide ; le code est corrigé.','4 / Les trois tests réussissent ; leurs résultats sont consultables.'][step];document.querySelector('#play').textContent=step===3?'Revoir le parcours':'Étape suivante';cards[step].scrollIntoView({behavior:'smooth',block:'nearest'});});</script></html>'''
    page = page.replace('<details><summary>', '<section class="card"><h2>Nouveau : vérifier les pièces réelles</h2><p>Le vérificateur distinct contrôle le reçu, le journal et les empreintes du code et des tests, avec une empreinte de référence capturée séparément par cet exécuteur local.</p><p>Résultats réels : test initial en échec ; version corrigée vérifiée sur trois tests ; autre version du code refusée ; référence fictive refusée.</p><a href="RUN/verification-summary.json">Consulter les quatre vérifications</a><p>Cette intégrité dépend de la confiance dans l’exécuteur et son empreinte de référence. Elle ne certifie ni une machine compromise, ni les fichiers non listés.</p></section><details><summary>')
    page = page.replace('<details><summary>', '<section class="card"><h2>Mode strict : poursuivre seulement après validation</h2><p>La chaîne de démonstration écrit son marqueur de clôture uniquement après un code de succès. Preuve manquante, autre version du code et tests en échec interrompent cette étape.</p><a href="RUN/strict-summary.json">Voir les quatre résultats du mode strict</a><p>Ce mode doit être activé et son code de sortie respecté par la chaîne qui clôture la tâche. Il ne bloque pas une application qui ignore ce résultat.</p></section><details><summary>')
    readable = '<section><h2>Comprendre le résultat et la prochaine action</h2><p>Messages produits par Botte lors de cette exécution, en français. Le résultat technique et le blocage strict restent inchangés.</p><div class="grid">'
    for label, message in human_results:
        lines = message.strip().splitlines()
        readable += ('<article class="card"><h2>' + html.escape(lines[0]) + '</h2>'
                     + ''.join('<p>' + html.escape(line) + '</p>' for line in lines[1:])
                     + '<a href="RUN/human-' + label + '.txt">Lire le message enregistré</a></article>')
    readable += '</div></section>'
    page = page.replace('<aside class="limit">', readable + '<aside class="limit">')
    readme = (SCRIPT_DIR / "README.md").read_text(encoding="utf-8")
    start = readme.index("## Pièces de l'exécution publiée")
    end = readme.index("Les rapports sont conservés", start)
    evidence = "## Pièces de l'exécution publiée\n\n" + "\n".join(
        f"- [{label}]({rel}/{name})" for label, name in (
            ("Rapport initial", "avant/rapport-agent.json"),
            ("Anomalie détectée par Botte", "01-audit-avant.json"),
            ("Tests avant : une erreur", "02-tests-avant.txt"),
            ("Tests après : trois réussites", "03-tests-apres.txt"),
            ("Rapport corrigé avec références", "apres/rapport-agent.json"),
            ("Nouvel audit : zéro constat", "04-audit-apres.json"),
            ("Contre-exemple : référence fictive", "controle-limite.json"),
            ("Résultat du contre-exemple", "05-audit-limite.json"),
            ("Tests du détecteur", "06-tests-detecteur.txt"),
            ("Résultats et provenance", "resultats.json"),
            ("Empreintes des pièces", "empreintes.json"),
            ("Nouveau : quatre vérifications des preuves", "verification-summary.json"),
            ("Reçu de la version corrigée", "apres-receipt.json"),
            ("Empreinte capturée séparément par l'exécuteur", "apres-trusted-receipt.sha256"),
            ("Mode strict et clôture conditionnelle", "strict-summary.json"),
            ("Message : vérifié sur ces tests", "human-valid.txt"),
            ("Message : preuve manquante", "human-missing.txt"),
            ("Message : code modifié", "human-wrong_version.txt"),
            ("Message : test échoué", "human-failed_tests.txt"),
        )
    ) + "\n\n"
    rendered_readme = readme[:start] + evidence + readme[end:]
    contract = os.path.relpath(repo / "skills/completion_proof/VERIFICATION.md", BASE).replace("\\", "/")
    if BASE != SCRIPT_DIR:
        rendered_readme = rendered_readme.replace("../../../skills/completion_proof/VERIFICATION.md", contract)
        rendered_readme = rendered_readme.replace("(real-fix.md)", "(" + os.path.relpath(SCRIPT_DIR / "real-fix.md", BASE).replace("\\", "/") + ")")
        rendered_readme = rendered_readme.replace("(evaluation/", "(" + os.path.relpath(SCRIPT_DIR / "evaluation", BASE).replace("\\", "/") + "/")
    write(BASE / "README.md", rendered_readme)
    if BASE != SCRIPT_DIR:
        for name in ("ameliorations.md", "parcours.svg"):
            content = (SCRIPT_DIR / name).read_text(encoding="utf-8")
            content = content.replace("(real-fix.md)", "(" + os.path.relpath(SCRIPT_DIR / "real-fix.md", BASE).replace("\\", "/") + ")")
            content = content.replace("(evaluation/", "(" + os.path.relpath(SCRIPT_DIR / "evaluation", BASE).replace("\\", "/") + "/")
            write(BASE / name, content.replace("../../../skills/completion_proof/VERIFICATION.md", contract))
    write(BASE / "demonstration.html", page.replace("RUN", html.escape(rel)))
    print(json.dumps({"execution": str(run), "page": str(BASE / "demonstration.html"), "before_findings": 1, "after_findings": 0, "tests": "3 passed", "limitation_confirmed": True}))

if __name__ == "__main__":
    main()
