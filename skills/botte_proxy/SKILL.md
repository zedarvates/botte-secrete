---
name: botte-proxy
description: Inspect and configure the HTTP proxy that transforms chat requests before forwarding to a chosen LLM endpoint. Compression is not reversible through the proxy; remote targets receive forwarded data. Check request compatibility, content integrity and measured provider usage before claiming savings.
---

# Botte Proxy

The proxy forwards HTTP requests to a configured upstream endpoint. Chat requests
are processed by the universal compressor, prefix alignment and, when enabled,
output shaping. Compatibility depends on the client's paths and request format;
the proxy is not a general guarantee for every agent or provider API.

## Compression and measurements

- `compress_messages()` calls the universal compressor with `reversible=False`.
  The proxy exposes no restore route or original-content retrieval guarantee.
- Text and log summaries can change representation. System messages also use
  the text transform. Retain original instructions and evidence, and compare
  actual behavior before routing a workflow through the proxy.
- Input counts use a rough `len(text) // 4` estimate. Dashboard savings and cost
  projections are estimates, not proof of billed token reduction or preserved
  answer quality. No fixed percentage gain is guaranteed.

## Endpoint and listener

Compression runs locally, then the request is sent to the configured target.
A remote or cloud target receives that data. Check the target and its handling
of content before forwarding it.

The CLI binds `0.0.0.0` by default. For a listener on this machine only, specify
`--host 127.0.0.1`. The target prefix is concatenated with the incoming request
path; avoid duplicating `/v1` between the target and client path.

```bash
# Client sends /v1/chat/completions; target is the upstream origin.
python -m skills.botte_proxy.cli proxy --host 127.0.0.1 --port 8787 --target http://localhost:11434
```

Point a compatible OpenAI client at `http://127.0.0.1:8787/v1`. Credentials,
when required by the selected upstream, can be supplied through an already
configured `BOTTE_API_KEY`; do not print them in reports.

The running process serves `/stats` and `/dashboard`. The separate CLI `stats`
command reads its own process's in-memory counters; it does not query another
running proxy. Use the running server's `/stats` endpoint for that process.

The compression routine itself does not call a model. The upstream LLM and the
host agent may consume model tokens; inspect provider usage and task quality
before claiming a saving.
