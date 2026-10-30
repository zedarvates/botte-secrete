# Parcimonia introduction — production draft

Prepared: 2026-10-30. English development preview. Target spoken duration:
75–90 seconds at a natural pace; confirm with a timed read before recording.
Nothing in this document establishes a recording, benchmark, deployment,
public listing, or published video.

## Spoken script

I’m building Parcimonia to help ChatGPT and Codex use their tools more carefully.
The idea is simple: before doing a large amount of work, check what the task
needs and choose a useful first step.

Here’s the current version. I give it a task, and it proposes a workflow and
a short list of relevant tools. If the request is unclear, it can abstain.
The agent still checks the tools and carries out the work.

For GitHub, it prepares a scoped research plan: search for pull requests,
read their current state, inspect relevant files, and check the exact commit.
That helps us keep the evidence tied to the change we’re reviewing.
It can also condense supplied results while retaining failures and revision details.

For software tests, it suggests what to verify and what evidence to keep.
Game testing is a future direction; real-time control needs a qualified adapter.

The cloud helpers are deterministic and don’t need an OpenRouter account.
The local Botte Secrète plugin has a separate runtime setup.

We’re preparing a public release. We’ll show what works, measure the results,
and improve it from real feedback.

## Recording storyboard

Record a real run against the candidate revision. Capture actual outputs with
their limitations visible. The timings below are an editing plan, not a claim
that these operations complete within those intervals.

| Approximate screen time | Record this | Keep visible or explain |
| --- | --- | --- |
| 0–12 s | A clean title and the task entered in ChatGPT or Codex. | “Development preview”; identify the surface actually recorded. |
| 12–29 s | Call `assess_task` for one clear GitHub task using a small inventory of tools actually available in that session. Then show one ambiguous request returning an abstention. | `status`, `intent`, tool suggestions and `capability_verified: false`. These are advisory outputs. |
| 29–52 s | Call `plan_github_research` for `zedarvates/botte-secrete`. Have the host use its connected GitHub reader to execute the proposed search. Select a PR from actual results, read its metadata, then call `summarize_github_evidence` on supplied observations. | Distinguish planning, the host's GitHub read and compaction. Show source URL, revisions, `merged`/`merged_at`, incomplete reads and retained failure counts. Any size comparison covers the supplied JSON, not billed tokens or total task cost. |
| 52–65 s | Assess a focused software-testing request. Show the host running the relevant check in the candidate checkout and retaining the command, exit code and tested revision. | The assessment did not run the tests. Use the actual outcome, including failures or environment limits. |
| 65–77 s | Assess a game playtest request. Show its missing prerequisites. | “Future integration”; adapter, measured capture/input latency and stop condition still required. Do not show a fabricated live game controller. |
| 77–90 s | Show the cloud/local setup distinction and the release status card. | Cloud deterministic helpers; local runtime installed separately; public directory submission pending until independently confirmed. |

If live GitHub access or a test environment is unavailable, retain that result
and reshoot the corresponding segment later. A plan-only recording must be
labelled plan-only. Remove private repository names, account identifiers and
credentials from the recording.

### Reproducible plan examples

Run from the repository root with its supported Python interpreter. These
examples produce proposals only and make no GitHub or model calls:

```python
import json
from skills.preflight.assessment import assess_task
from skills.preflight.github_plan import plan_github_research

# Supply names/descriptions from the actual connected tool inventory for the
# recorded run. An empty inventory deliberately abstains on tool selection.
print(json.dumps(assess_task("Search GitHub pull requests", available_tools=[]), indent=2))
print(json.dumps(plan_github_research("zedarvates/botte-secrete", "preflight"), indent=2))
print(json.dumps(assess_task("Run regression tests", available_tools=[]), indent=2))
print(json.dumps(assess_task("Playtest the video game", available_tools=[]), indent=2))
```

After the real search, pass an exact returned PR number as `pr_number` to
`plan_github_research`. Do not insert a convenient historical number or imply
that a closed PR is merged. Reread metadata after checks; a changed head
invalidates evidence collected for the previous head.

## YouTube title and description

**Title:** Parcimonia: Practical Workflow Helpers for ChatGPT and Codex

**Description draft:**

Parcimonia is a project I’m building to help ChatGPT and Codex prepare useful
first steps, select relevant tool candidates, and keep evidence tied to the
work being checked.

This development preview covers advisory task assessment, GitHub research
plans, software-test preparation, and the prerequisites for future game
playtesting. The cloud helpers use deterministic code. The Botte Secrète
local plugin requires a separately installed runtime.

No OpenRouter account is required for these deterministic helpers. Codex
usage still follows your authentication method, plan and usage limits.
This preview makes no measured speed or token-savings claim.

We’re preparing public distribution and will add verified installation details
when the release is ready. Subscribe for practical demonstrations and updates.

Before upload, replace this paragraph with the actual recorded revision,
verified release link, supported surfaces and current distribution status.
Do not publish placeholder installation or directory links.

## Release and claims gates

| Claim or step | Evidence required before saying it | Current production status |
| --- | --- | --- |
| “Task assessment proposes a workflow.” | Candidate outputs and relevant behavior tests for `assess_task`; preserve ambiguity and abstention cases. | Implementation added in this change; attach root verification results before recording. |
| “GitHub research plan.” | Actual `plan_github_research` output with bounded repository scope; actual GitHub reads shown separately. | Advisory planner, not a GitHub transport or search executor. |
| “Software tests were run.” | Command, environment, exit code and tested revision from the recorded run. | Not established by an assessment output. |
| “Game testing.” | Qualified adapter, scenario, captures, bounded inputs, assertions, latency measurements and stop mechanism. | Future direction; no real-time capability claimed. |
| “No OpenRouter account for these cloud helpers.” | Confirm the recorded helpers use deterministic code with no model backend call or provider key requirement. | Scoped to these helpers; host usage remains subject to the host plan. |
| “Install the local Botte Secrète plugin.” | Fresh install with compatible separately installed runtime; restart session and confirm tools. | Plugin installation alone does not install Python, runtime, models or credentials. |
| “Available in the public directory.” | Approved and published listing, exact listing URL, and a fresh-account installation on each advertised surface. | Pending. A Git marketplace or private MCP connection does not establish this. |
| “Faster” or “uses fewer tokens.” | Paired comparable tasks, accepted-result quality, end-to-end timing and actual provider/host usage, including helper overhead and retries. | No such claim approved by this draft. UTF-8 byte reduction is a separate measurement. |
| Publish the video | Final timed read, actual recording, evidence links, verified installation instructions and user-selected destination. | Script and shot plan only; no recording, upload or publication performed. |

The new helpers do not execute tools, authorize actions, activate model routing,
or provide real-time game control. Existing optional local model workflows are
a separate setup and must be demonstrated separately.

## Production source notes

Official pages read on 2026-10-30. Recheck them and the actual publication state
before recording installation instructions:

- [Plugins and supported surfaces](https://learn.chatgpt.com/docs/plugins):
  skills and MCP tools, supported surfaces, installation and new-session behavior.
- [Authentication](https://learn.chatgpt.com/docs/auth): ChatGPT subscription
  authentication versus separately billed API-key usage; cloud authentication.
- [Pricing and usage](https://learn.chatgpt.com/docs/pricing): Work and Codex
  share usage; context and tool use affect consumption.
- [Build and distribute plugins](https://developers.openai.com/plugins/build/plugins):
  portable packaging, separate local/repository marketplaces and public-directory
  submission; public-directory restrictions on lifecycle hooks.
- [Remote MCP review and publication](https://developers.openai.com/plugins/deploy/app-review):
  verified publisher, public endpoint, review requirements, approval and the
  separate Publish action.

The GitHub planner emits public API source URLs under
`https://api.github.com/repos/zedarvates/botte-secrete` and
`https://api.github.com/search/issues`, with source links under
`https://github.com/zedarvates/botte-secrete`. These are proposed read targets,
not proof that the reads happened. Use the authenticated GitHub connector
available to the host for the actual recording; preserve its access boundaries.

Keep these evidence fields with the final production notes: tested revision,
date, actual surface, helper/runtime version, commands, check results, returned
GitHub URLs and commit SHAs, pagination limits, and final release status.
