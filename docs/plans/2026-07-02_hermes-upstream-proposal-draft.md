# DRAFT — for human review before posting anywhere

> **Do not publish as-is.** This is a starting draft for an issue/discussion
> on the hermes-agent repo, written from the botte-secrète side without
> access to that repo's actual code, issue templates, or maintainer norms.
> Before posting: (1) verify the claims below against the real hermes-agent
> codebase, (2) adjust tone/format to match their contribution norms, (3) have
> a human actually send it. This is public communication on behalf of the
> project — it doesn't go out on my say-so.

---

## Suggested title

"Efficiency integration: pluggable local-first routing belt (opt-in, zero
required changes)"

## Suggested body

Hi — I maintain [botte-secrète](https://github.com/zedarvates/botte-secrete),
a local-first token-routing layer (micro-NN classifiers → deterministic
rules → local LLM → cloud, cheapest-first) that sits in front of an agent's
model calls and intercepts the trivial ones for 0 tokens.

I think it pairs well with Hermes-Agent's second-brain pattern: every task
that goes through Goal Filter → Knowledge Retrieval → History Check still
calls a model even for trivial work (renames, classification, short
summaries). Botte's belt can intercept exactly that tier before it reaches
Hermes' model call.

This is **opt-in and additive** — no changes requested to hermes-agent's
core. Two ways to wire it in, whichever fits Hermes' actual architecture:

1. **MCP** — botte already ships a standard MCP server; if Hermes' tool layer
   supports MCP, it's a one-line config addition, no code.
2. **Function-calling bridge** — a small adapter
   ([`hermes_bridge`](../../skills/hermes_bridge/)) exposes 5 core tools
   (auto_route, local_chat, fusion, find_skills, infra_tips) as OpenAI-style
   function specs + a dispatcher, for frameworks that predate/don't use MCP.

**The numbers, not just the pitch:** `python -m skills.bench.cli` runs a
fixed, versioned task corpus through the real routing decision logic (0
tokens spent measuring) and reports the actual savings against a
"no-routing" baseline — see [`docs/integrations/hermes.md`](../integrations/hermes.md)
for the full writeup and the bench's stated caveats (results depend on real
prompt shapes; the reference corpus is intentionally short/reproducible, not
exhaustive).

Happy to open a PR with the integration doc if there's interest, or to adjust
the bridge's tool shape to match whatever Hermes actually expects — I
haven't had a chance to look at the tool-registration internals yet, so take
the "function-calling adapter" description as a starting guess subject to
correction.

---

## Reviewer checklist before this goes out

- [ ] Confirm hermes-agent repo URL and current architecture (has it changed
      since `hermes-second-brain/DESIGN.md` was written?)
- [ ] Confirm whether they use MCP, OpenAI function-calling, or something else
      entirely — adjust "Path A/B" framing or drop what doesn't apply
- [ ] Confirm the repo's contribution norms (issue vs. discussion vs. PR-first)
- [ ] Run `python -m skills.bench.cli` fresh and paste real numbers, not a
      placeholder reference
- [ ] Have a human post it — not an automated step
