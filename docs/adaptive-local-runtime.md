# Adapt local inference to your machines and memory

The canonical [runtime setup guide](../skills/llm_backends/runtime-guide.md)
ships beside the `llm_backends` skill, so your own LLM can read it after a
package installation as well as from a GitHub checkout.

It contains English and French setup instructions, portable host/engine
profiles, shared and external memory adapters, explicit task routing, paired
benchmarks and replay-safe observation capture. Native speculative decoding
must already be supported and configured in the target engine; a profile alone
does not activate it or prove a speedup.

```bash
botte runtime inspect
botte runtime template --topology single --memory none
botte runtime schema
```
