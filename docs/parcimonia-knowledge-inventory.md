# Parcimonia knowledge, retrieval and graph inventory

Source audit: 2026-10-30. This inventory separates available source code,
documented interfaces, draft experiments and an actually connected runtime.
It does not import a private corpus or activate a route.

## Existing components

| Component | Observed implementation | Boundary and reference |
| --- | --- | --- |
| Botte Memory Hub | SQLite storage per project; typed wiki/code-graph/fact/decision records; search, context bundles, lifecycle and provenance; local MCP handlers | A `wiki` asset type is not a wiki crawler or an automatically populated knowledge base. External/generated observations remain quarantined and non-executable. [Store](https://github.com/zedarvates/botte-secrete/blob/992947158fb1b7e291cb2407158fac8964729d21/skills/memory_hub/store.py), [quarantine contract](https://github.com/zedarvates/botte-secrete/blob/992947158fb1b7e291cb2407158fac8964729d21/docs/memory-quarantine.md), [MCP handlers](https://github.com/zedarvates/botte-secrete/blob/992947158fb1b7e291cb2407158fac8964729d21/skills/memory_hub/mcp.py). |
| Botte capability registry | Builds a capability catalogue from skill metadata, organized into six layers; the Conductor uses it for plan construction | Metadata describes candidates; it does not qualify installed tools or source truth. [Registry](https://github.com/zedarvates/botte-secrete/blob/992947158fb1b7e291cb2407158fac8964729d21/skills/capabilities/registry.py). |
| Botte DAG/RAG utilities | Graph execution waves, memoized node outputs, exact document-hash deltas, query shortening and lexical agent selection | These operations do not implement semantic wiki retrieval, graph reasoning, source freshness validation or a corpus index. [Implementation](https://github.com/zedarvates/botte-secrete/blob/992947158fb1b7e291cb2407158fac8964729d21/skills/dag_optimizer/cli.py). |
| Botte audit graph | Addressable findings, explicit relations and deterministic traversal from an audit report | An audit graph is a graph of findings, not a general knowledge graph or proof of causal relations. [Audit graph](https://github.com/zedarvates/botte-secrete/blob/992947158fb1b7e291cb2407158fac8964729d21/skills/audit_dag/dag.py). |
| Botte pipeline DSL | Named steps, declared dependencies and failure behavior, composed through the existing MetaHarness | A pipeline definition does not establish that every named adapter is installed or that the pipeline was executed. [DSL](https://github.com/zedarvates/botte-secrete/blob/992947158fb1b7e291cb2407158fac8964729d21/skills/meta_harness/pipeline_dsl.py). |
| Botte local LLM client | Local-backend chat and constrained-JSON helpers | Backend presence, loaded models, retrieval quality and successful task completion require separate observations. [Client](https://github.com/zedarvates/botte-secrete/blob/992947158fb1b7e291cb2407158fac8964729d21/skills/llm_backends/client.py). |
| Botte vector protocol | Fixed structured-finding features and an in-memory cosine-similarity store | Not learned text embeddings, a persistent vector database or a Qdrant deployment. [Documented limits](https://github.com/zedarvates/botte-secrete/blob/992947158fb1b7e291cb2407158fac8964729d21/skills/vector_protocol/SKILL.md). |

The pinned Botte revision above is the inspected candidate, not a claim that all
of its draft changes have been merged or installed in the connected cloud host.
Historical ADR status can lag the code; inspect the implementation and current
runtime instead of treating a proposed design as an activation receipt.

## Parcimonia memory and local retrieval

Two independent draft pull requests contain relevant code. Both were open,
draft and unmerged when observed. Their exact heads each had two successful
hosted checks, Python 3.10 and Python 3.14; those checks do not establish a live
homelab integration.

| Candidate | Code and documentation | Established scope |
| --- | --- | --- |
| [PR 12](https://github.com/zedarvates/parcimonia/pull/12), `6d9ce62201f5b3c5c77313a3451e8a1096c5e26e` | [Compact memory](https://github.com/zedarvates/parcimonia/blob/6d9ce62201f5b3c5c77313a3451e8a1096c5e26e/docs/COMPACT_MEMORY.md), [replay](https://github.com/zedarvates/parcimonia/blob/6d9ce62201f5b3c5c77313a3451e8a1096c5e26e/docs/MEMORY_REPLAY.md), [capture](https://github.com/zedarvates/parcimonia/blob/6d9ce62201f5b3c5c77313a3451e8a1096c5e26e/docs/MEMORY_CAPTURE.md), [existing-run attachment](https://github.com/zedarvates/parcimonia/blob/6d9ce62201f5b3c5c77313a3451e8a1096c5e26e/docs/MEMORY_EXECUTION.md) | Bounded references; exact versioned fact retrieval and verifier identity; explicit missing evidence; replay/capture of caller-owned episodes. No automatic corpus ingestion, model/provider call, active-router replacement or real-usage saving established. |
| [PR 17](https://github.com/zedarvates/parcimonia/pull/17), `ea126dc1a41090df5cb840c9b08602b37e42a803` | [Knowledge guide](https://github.com/zedarvates/parcimonia/blob/ea126dc1a41090df5cb840c9b08602b37e42a803/docs/LOCAL_KNOWLEDGE.md), [retrieval adapter](https://github.com/zedarvates/parcimonia/blob/ea126dc1a41090df5cb840c9b08602b37e42a803/src/tiberium_ai/local_retrieval.py), [worker](https://github.com/zedarvates/parcimonia/blob/ea126dc1a41090df5cb840c9b08602b37e42a803/examples/local_chat_worker.py) | Explicit context-file mode or one caller-selected external vault `rag` command followed by at most one local model request. Bounded streams/deadlines and versioned receipts; failed retrieval blocks inference. Fixture-based integration tests do not qualify the real vault script, index, LM Studio or hardware. |

PR 17 deliberately reuses an existing vault engine. Its documented command is
`python tools/rag_dag_engine.py rag --query QUESTION --top 3`; that script belongs
to the vault, not to Parcimonia. The adapter prepares document context and
requests citations. It neither creates another wiki nor updates model weights.
The recorded context hash identifies bytes, not their truth or freshness.

Private documentation for the existing corpus and its RAG/DAG guide was also
read during this audit. It describes a Markdown corpus, SQLite FTS5/BM25 search,
declared note relations and citation-bearing context preparation. This audit
did not inspect or run the actual vault files/index on a workstation. Private
note text, filesystem paths and corpus links are deliberately not copied into
this public source document; the owner can consult the existing Space directly.

## Other relevant draft experiments

| Candidate | Current observed status | Limit |
| --- | --- | --- |
| [Needle memory pilot, PR 117](https://github.com/zedarvates/botte-secrete/pull/117), `02be6033c7a73788643ee5e7cf6ad6e071394e02` | Open, draft, unmerged; consultative memory-tool proposals | The reported threshold study stopped for insufficient safe coverage. It is not an activated memory router. |
| [Capability Graph v0, PR 134](https://github.com/zedarvates/botte-secrete/pull/134), `0bfb5a299a4f7d284d74c1f531ffa96efe7f7939` | Open, draft, unmerged; JSON schema only | A schema is not a runtime graph engine or a deployed integration. |
| [RSI graph observer, PR 136](https://github.com/zedarvates/botte-secrete/pull/136), `59aa9fda3f5b7b46e014ce86036fd006ed1613c5` | Open, draft, unmerged; read-only temporal event adjacency with explicit provenance | No candidate promotion, causal proof, policy/model mutation or measured savings. |

## Reuse for the verification workbench

Keep documentary knowledge, execution evidence and authority separate. A useful
connection uses the existing source URI/version/hash and the exact case,
environment, tool revision and outcome; it does not promote an inferred link
to a verified fact.

- A reduced reproduction can retain the original failure signature and links
  to the original input and documentation. A different failure is not a valid
  reduction of the original bug.
- Test priority can consume observed durations/failures, but a remembered fast
  check does not replace required final checks or prove the current code passes.
- Cloud/local conformance can bind both source revisions and compare declared
  invariants while preserving intentional implementation differences.
- Mutation checks test the strength of a verifier on disposable copies. A killed
  mutant is scoped evidence; surviving mutants identify a test gap.
- Interface exploration produces an observed state/action graph. Observed edges,
  declared transitions and unvisited areas stay distinct; a state graph may
  contain cycles and is not automatically a DAG.
- Intermittent-failure triage retains every attempt and its seed/context.
  A retry pass does not erase a prior failure or prove general reliability.

The [verification-memory connection](parcimonia-verification-memory.md) now
maps the six helper schemas to private quarantine proposals in the existing
Memory Hub and reviews supplied documentary links. Preview is read-only;
persistence needs an explicit destination and does not enter normal context.
The [recall adapter](parcimonia-memory-recall.md) searches bounded sanitized
receipt projections in an explicitly selected closed/checkpointed database,
returning source versions and declared report/document digests. It preserves
quarantine and distinguishes incomplete or unavailable reads from empty results.
An optional explicit inventory connects these selected references to the
existing documentary reviewer by exact URI/version, retaining ambiguity,
missing/unknown references and version mismatches without creating graph edges.
The separate Parcimonia episode format still requires its own versioned adapter.
This inventory alone adds neither a store nor an automatic memory write.
