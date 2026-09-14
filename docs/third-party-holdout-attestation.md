# Third-party holdout attestation

Purpose: allow an external collaborator to test a frozen Botte/target candidate against cases that remain entirely under the collaborator's control.

This protocol is designed for Cole Medin, Stefan Vaskevich, or any other independent maintainer. They do **not** need to send us their cases, prompts, assets, expected answers, local paths, credentials, or private repository data.

## What the third party keeps private

- the holdout cases themselves;
- expected outcomes;
- any private project data used to construct those cases;
- per-case results, unless the collaborator voluntarily shares them;
- local environment details not needed for reproducibility.

## What they may publish back

Only a public-safe attestation such as:

```json
{
  "schema": "botte.factory-third-party-holdout/v1",
  "candidate_sha": "<40-char candidate SHA>",
  "candidate_tree": "<40-char Git tree SHA if available>",
  "set_digest_sha256": "<64-char digest of their private set>",
  "case_count": 16,
  "status": "pass",
  "issuer": "<their chosen public identity>",
  "issuer_kind": "independent-third-party",
  "independent_third_party": true,
  "contains_cases": false,
  "notes": "optional bounded note"
}
```

The digest proves the private set was fixed for that report; it does not reveal the set.

## Rules

1. Test an exact immutable candidate SHA, never `main` or a moving branch.
2. Keep holdout cases outside our repository and outside the candidate's builder-visible context.
3. Run your own project tests/review independently of Botte.
4. Treat Botte findings as hypotheses until you reproduce them.
5. Do not include private case payloads or credentials in the attestation.
6. `status=pass` means only that the chosen private set passed under the stated evaluator. It is not certification of security, correctness, licensing, artistic quality, or production readiness.
7. A third-party pass may strengthen evidence for the tested operation class, but it never grants automatic merge/deploy/promotion authority.
8. A failure is equally valuable: report `status=fail` without disclosing the case, then optionally provide a minimal public reproduction if safe.

## Candidate for the current external pilot

The frozen Botte Secrete external-pilot candidate is:

`d98505fd6586ff3d0d32a2cb4ebd5f0408d4142a`

Install exactly that SHA:

```bash
python -m pip install "git+https://github.com/zedarvates/botte-secrete.git@d98505fd6586ff3d0d32a2cb4ebd5f0408d4142a"
```

For StoryCore MusicPlan holdout testing, use the exact target head recorded in the pilot request rather than the latest branch state.

## Evidence interpretation

Independent third-party evidence is stronger than an operator-authored private holdout because the candidate authors cannot tune against unknown cases. It is still bounded evidence: confidence applies only to the candidate identity, evaluator, operation class, and hidden set represented by that attestation.
