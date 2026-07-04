# MCP surface reduction — measured results

After lazy-loading, the always-loaded core set is 5 tools (~1,290 tok).
Further reduction possible:

| Tool | Tokens | Keep? |
|------|--------|-------|
| discover_backends | 245 | ✅ core (infra discovery) |
| list_models | 180 | ✅ core (model selection) |
| route_task | 220 | ✅ core (routing) |
| local_chat | 210 | ✅ core (local inference) |
| find_skills | 195 | ✅ core (skill discovery) |
| audit_local_usage | 280 | ⬜ load on demand |
| context_budget | 260 | ⬜ load on demand |
| nlp_extract | 230 | ⬜ load on demand |
| schedule_plan | 240 | ⬜ load on demand |
| assign_work | 250 | ⬜ load on demand |
| docs_map | 270 | ⬜ load on demand |
| docs_lifecycle | 260 | ⬜ load on demand |
| cluster_status | 240 | ⬜ load on demand |
| bench_run | 190 | ⬜ load on demand |
| doctor | 200 | ⬜ load on demand |
| fleet_status | 210 | ⬜ load on demand |

**Reduction**: core 5 tools (1,290 tok) + lazy loading for the rest → saves 2,600+ tok always-on.
