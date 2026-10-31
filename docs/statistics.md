# Statistics as a deterministic task

Parcimonia's advisory `assess_task` can propose the `statistics` intent for an
explicit calculation request in French or English. It shortlists tools supplied
by the host; it does not execute the calculation or verify tool availability.
The Botte Python runtime provides the separate `compute_statistics` MCP tool.

The calculator accepts supplied numeric values and performs no model call,
network request or file access. It does not extract observations from prose,
fetch measurements or select an inferential model. The host chooses the data,
units and requested measures, then interprets the result.

## One contract for Python, CLI and MCP

```json
{
  "values": [10, 20, 30, 40],
  "operations": ["count", "sum", "mean", "median"],
  "percentiles": [50, 95],
  "missing": "reject"
}
```

```python
from skills.solvers import compute_statistics

result = compute_statistics([10, 20, 30, 40], percentiles=[95])
assert result["results"]["mean"] == 25
assert result["percentiles"][0]["value"] == 38.5
```

For the CLI, pipe that JSON object into `python -m skills.solvers.cli stats`.
The CLI limits input to 1,000,000 UTF-8 bytes, outputs JSON and exits with code 2
on invalid arguments. For MCP, discover `compute_statistics` through the existing
`find_tool` and read its schema before calling it. It stays outside the always
listed tool core.

Supported operations are `count`, `sum`, `min`, `max`, `mean`, `median`,
`variance_population`, `variance_sample`, `stdev_population` and `stdev_sample`.
The default operations are the first six. Only requested measures are computed.
Sample variance and sample standard deviation require at least two usable values.

Percentiles use linear type-7 interpolation: sort the usable data, let
`h = (n - 1) * percentile / 100`, then interpolate between adjacent ranks.
Percentiles 0 and 100 return the minimum and maximum. This convention is explicit;
other methods may yield different results for a small sample.

## Input and output boundaries

Inputs are bounded to 10,000 values and 16 requested percentiles. Only finite
Python/JSON numbers are accepted. Booleans and numeric strings are rejected.
Integer magnitudes above `2**53` are rejected to avoid silent loss on conversion
to binary64. Calculations use binary64 and remain subject to floating-point
rounding; deterministic does not mean arbitrary-precision arithmetic.

`missing="reject"` is the default. Only explicit `missing="omit"` permits
discarding null/None entries; the result reports the input, usable and omitted
counts. An empty usable series, unknown operation, duplicate request,
out-of-range percentile or non-finite result fails explicitly. Units are the
caller's responsibility; variance has squared units.

The `botte.statistics/v1` result states methods and contains a compact `results`
object, a list of computed `percentiles`, and execution metadata. It does not
echo the dataset or infer billed token, price or latency savings.

## Scope and verification

This increment extends the Python runtime and its advisory assessor. It does
not update the separately hosted JavaScript cloud helpers or enable an automatic
route in the standalone Parcimonia repository. That router can use the same
arguments in `Task.inputs` with kind `statistics`; a future execution adapter must
bind output evidence to the exact input and calculator version.

Tests cover known arithmetic results, interpolation conventions, missing-data
policy, invalid inputs, limits, strict JSON, MCP discovery and execution, the
CLI boundary and French/English task selection. Synthetic measurements validate
calculation behavior; they do not establish a performance gain on real workloads.
