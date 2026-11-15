# Prepare a cited request from document context

`botte verify answer-request` turns the output of the
[document-context reader](parcimonia-document-context.md) into a bounded request
mapping compatible with the existing `LocalLLMClient.chat` interface. It performs
no inference, model discovery, backend selection, network call or memory write.

```sh
botte verify answer-request --input context.json \
  --question "What do these sources establish?" --model CALLER_DECLARED_MODEL
```

The model name is optional caller metadata. It does not establish installation,
suitability or a functioning backend. Preparation does not instantiate the
client, activate a route, or send the returned mapping. Existing runtime and
permission checks apply to any later invocation.

## Ready and abstained

Input must use the existing `parcimonia.document-context/v1` or
`parcimonia.recalled-document-context/v1` contract. The helper takes an owned JSON
snapshot, binds its digest and checks coverage, raw-file pin agreement, excerpt
digests and citation consistency. It retains reported outcomes and known
upstream uncertainty. It cannot authenticate the supplied report or rehash an
unavailable original file from its excerpt.

Output uses `parcimonia.grounded-request/v1`:

| Status | Meaning |
| --- | --- |
| `ready` | The bounded input contract passed and `chat_kwargs` is present as data. |
| `abstained` | Required evidence or consistency is missing; reasons are retained and no `chat_kwargs` is provided. |

Incomplete, unavailable or finding-bearing contexts abstain, as do known
upstream contradictions, no usable excerpts, tampered excerpts and budget
overflow. Source omissions cannot leave a partial request marked ready. Unknown
versions are rejected as an abstention. Invalid command arguments or unreadable
input files return the existing CLI error envelope.

`ready` means request preparation succeeded. It does not mean an answer was
generated, supported, correct or secure, or that the excerpts cover the complete
documents or corpus. Recheck the target runtime and source applicability before
using the mapping. There is no automatic retry or invocation on resumption.

## Citations and data boundaries

Each source gets a stable `citation_id` derived from URI, declared version,
raw-file hash, excerpt hash and exact citation bounds. Returned `sources` maps
those IDs back to provenance. IDs do not depend on input ordering or the model
name. Hashes identify supplied bytes and metadata, not their truth or freshness.

Fixed instructions remain in `chat_kwargs.system`. The question, excerpt text,
citation metadata, scope limits and reported outcomes are JSON data in
`chat_kwargs.prompt`. The fixed instructions request a JSON answer with supplied
citation IDs and abstention if evidence is insufficient. Embedded document
commands are never copied into the system instructions or executed here.
This separation and JSON formatting do not qualify a model's resistance to
prompt injection or its citation accuracy. Answer verification is outside this
increment.

The mapping uses the existing chat arguments: prompt, system, temperature,
max_tokens, response_format and optional model. It does not modify the client or
claim support by a particular server. Request limits count canonical compact
ASCII JSON bytes, not provider tokens. Defaults: 8 sources, 32 KiB request
mapping and 64 KiB final envelope; options expose these limits.

CLI exit codes: 0 for `ready`, 2 for abstention or invalid input. Retain the
context/request digests, source identities, reasons and unknowns with the existing
task evidence. Publishing a prepared mapping may expose selected document text;
use the task's actual sharing scope rather than treating preparation as sharing
authorization.
