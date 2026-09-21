"""Human-readable verification results; machine statuses stay unchanged."""

COPY = {
    "fr": {
        "announced": ("Annoncé — pas encore vérifié", "Ce rapport ne contient pas une déclaration de fin prise en charge.", "Fournir le rapport de fin et son reçu d'exécution."),
        "missing_evidence": ("Preuve manquante", "Une référence ou un fichier nécessaire manque.", "Récupérer les pièces auprès de l'exécuteur des tests."),
        "invalid_evidence": ("Preuve invalide", "Les pièces ne permettent pas de confirmer ce résultat.", "Contrôler le reçu attendu et les fichiers cités."),
        "test_failed": ("Test échoué", "Les pièces correspondent au reçu, mais l'exécution enregistrée n'a pas réussi.", "Corriger le problème et produire une nouvelle exécution avec ses preuves."),
        "verified_on_recorded_tests": ("Vérifié sur ces tests", "Les pièces et les fichiers listés correspondent au reçu de tests réussis.", "Conserver ce reçu avec le résultat ; revérifier après toute modification."),
        "io": ("Vérification impossible", "Un dossier ou un fichier ne peut pas être lu.", "Vérifier les chemins et les droits d'accès, puis relancer le contrôle."),
        "source_hash_mismatch": ("Le code ou les tests ont changé depuis l'exécution enregistrée.", "Relancer les tests sur cette version et obtenir un nouveau reçu."),
        "log_hash_mismatch": ("Le journal ne correspond pas à l'empreinte enregistrée.", "Récupérer le journal original ou refaire l'exécution."),
        "receipt_hash_mismatch": ("Le reçu ne correspond pas à la référence de confiance fournie.", "Demander le reçu attendu à l'exécuteur, sans reprendre l'empreinte du rapport."),
        "run_id_mismatch": ("Le rapport et le reçu désignent des exécutions différentes.", "Associer le rapport au reçu attendu pour cette tâche."),
        "scope": "Portée : uniquement les tests enregistrés et les fichiers listés ; exécuteur de confiance requis.",
        "counts": "{tests} test(s) enregistré(s) ; {files} fichier(s) contrôlé(s).",
        "next": "Suite : ",
        "no_tests_executed": ("Tous les tests ont été ignorés : aucun test n'a été exécuté.", "Exécuter au moins un test réel et produire un nouveau reçu."),
        "skipped": "{executed} test(s) exécuté(s) ; {skipped} ignoré(s).",
    },
    "en": {
        "announced": ("Announced — not yet verified", "This report is not a supported completion claim.", "Provide the completion report and its execution receipt."),
        "missing_evidence": ("Missing evidence", "A required reference or file is missing.", "Obtain the artifacts from the test executor."),
        "invalid_evidence": ("Invalid evidence", "The artifacts do not establish this result.", "Check the expected receipt and referenced files."),
        "test_failed": ("Test failed", "Artifacts match the receipt, but the recorded execution did not succeed.", "Fix the problem and capture a new execution with its evidence."),
        "verified_on_recorded_tests": ("Verified on these tests", "Artifacts and listed files match the passing test receipt.", "Keep the receipt with the result; verify again after any modification."),
        "io": ("Unable to verify", "A directory or file cannot be read.", "Check paths and access permissions, then retry verification."),
        "source_hash_mismatch": ("Code or tests have changed since the recorded execution.", "Run tests on this version and obtain a new receipt."),
        "log_hash_mismatch": ("The log does not match its recorded digest.", "Obtain the original log or repeat the execution."),
        "receipt_hash_mismatch": ("The receipt does not match the supplied trusted digest.", "Obtain the expected receipt from the executor, not the agent report's digest."),
        "run_id_mismatch": ("The report and receipt identify different executions.", "Use the receipt expected for this task."),
        "scope": "Scope: recorded tests and listed files only; a trusted executor is required.",
        "counts": "{tests} recorded test(s); {files} checked file(s).",
        "next": "Next: ",
        "no_tests_executed": ("All tests were skipped: no test was executed.", "Execute at least one actual test and capture a new receipt."),
        "skipped": "{executed} executed test(s); {skipped} skipped.",
    },
}


def format_result(result: dict, language: str = "fr") -> str:
    copy = COPY[language]
    status = result.get("status")
    errors = result.get("errors") or []
    if status not in {"announced", "missing_evidence", "invalid_evidence",
                      "test_failed", "verified_on_recorded_tests"}:
        status = "invalid_evidence"
    if status == "verified_on_recorded_tests" and (
            result.get("verified") is not True or result.get("errors") != []):
        status = "invalid_evidence"
    if any(code in {"root_or_io_error", "unreadable_file"} for code in errors):
        status = "io"
    title, reason, action = copy[status]
    for code in errors:
        if code in {"source_hash_mismatch", "log_hash_mismatch",
                    "receipt_hash_mismatch", "run_id_mismatch", "no_tests_executed"}:
            reason, action = copy[code]
            break
    lines = [title, reason]
    if type(result.get("tests_run")) is int and result["tests_run"] > 0:
        lines.append(copy["counts"].format(tests=result["tests_run"],
                                            files=len(result.get("source_files_checked", []))))
    lines.extend([copy["next"] + action, copy["scope"]])
    if type(result.get("tests_skipped")) is int and result["tests_skipped"] > 0:
        lines.insert(-2, copy["skipped"].format(executed=result.get("tests_executed", 0),
                                               skipped=result["tests_skipped"]))
    return "\n".join(lines)
