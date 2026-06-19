---
name: docgen
description: Generate documentation with a local model drafting and the cloud only refining (0 cloud tokens for the draft), plus a local session review that summarises what a work session did. Use to write README/module docs/CHANGELOG/guides/ADRs cheaply, or to produce end-of-session notes/learnings from a transcript.
---

# docgen — local-drafted docs (cloud-refined) + session review

Documentation is verbose, so the LOCAL model writes the first draft and the cloud
model is spent only on a final polish — the video's "pre-write local, correct
with cloud" pattern, built on [[auto_router]]'s `draft_refine` fusion.

```bash
python -m skills.docgen.cli draft "deploy the service" --kind guide
python -m skills.docgen.cli draft "auth module" --kind module
python -m skills.docgen.cli session ~/.claude/projects/.../transcript.jsonl
python -m skills.docgen.cli session "user: did X\nassistant: built Y" --text
```

- **draft** — local model drafts (`readme|module|changelog|guide|adr`); cloud
  refines **only if a key is set** (otherwise you keep the local draft, marked
  un-refined). 0 cloud tokens for the draft itself.
- **session** — reads a transcript (Claude Code `.jsonl`, markdown, or raw text)
  and a LOCAL model returns `done / decisions / learnings / next`. 0 cloud tokens.

Exposed via [[llm_mcp]] as `draft_doc` and `session_review`. Pairs with
[[ingest]] (pull sources to document) and [[checkup]] (what changed this session).
