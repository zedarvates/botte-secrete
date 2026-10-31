---
name: portfolio_sync
description: Validate a private portfolio registry and compare it with a pre-fetched GitHub repository inventory. Strictly read-only, deterministic, standard-library only, no network and no cloud tokens. Use to detect unregistered repositories, stale entries, visibility drift, archive drift, duplicate project IDs, forbidden absolute paths, or accidentally stored credentials before proposing changes to the project cockpit.
---

# portfolio_sync — read-only project cockpit validation

`portfolio_sync` validates a registry supplied explicitly by the caller. The
registry is an index, never a source of code truth, and must live outside this
public repository when it contains private project metadata.

```bash
python -m skills.portfolio_sync.cli validate --registry /path/to/private/projects.json
python -m skills.portfolio_sync.cli summary --registry /path/to/private/projects.json
python -m skills.portfolio_sync.cli diff \
  --registry /path/to/private/projects.json \
  --observed /path/to/sanitized-repositories.json \
  --json
```

## Safety contract

- no network calls;
- no GitHub, Memory Hub, Kanboard, filesystem, production, or publication writes;
- reads only the explicitly supplied registry and optional observed inventory;
- no repository-local default for the private registry;
- rejects duplicate IDs and duplicate GitHub sources;
- rejects undeclared statuses and priorities;
- rejects credentials under common secret-bearing keys;
- rejects absolute local paths, including Windows drive and UNC paths;
- reports differences but never repairs them automatically.

The observed inventory accepts a list of GitHub API-like repository objects,
plain `owner/repo` strings, or an object containing `repositories`, `items`, or
`repos`. Only `full_name`, visibility/private, and archived state are consumed.

A later write-capable integration must remain a separate skill, require explicit
owner confirmation, and consume reviewed output from this read-only layer.
