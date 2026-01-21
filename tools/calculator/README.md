# Exact Computation / Calculator Tool (v1)

Minimal, deterministic HTTP service for high-precision arithmetic, statistics,
and unit-safe calculations. Stateless, no auth, no network calls.

## HTTP API

### `GET /health`
Response:
```json
{"status":"ok"}
```

### `POST /mcp`
MCP JSON-RPC tool call endpoint.

Tool name: `exact_compute`

Request example:
```json
{
  "jsonrpc": "2.0",
  "id": "req-1",
  "method": "tools/call",
  "params": {
    "name": "exact_compute",
    "arguments": {
      "operation": "arithmetic",
      "params": {
        "operator": "add",
        "operands": ["1.25", "2.75"],
        "precision": 28
      }
    }
  }
}
```

Response example:
```json
{
  "jsonrpc": "2.0",
  "id": "req-1",
  "result": {"operation":"arithmetic","result":"4.0"}
}
```

### `POST /v1/compute`
Request schema (JSON):
```json
{
  "operation": "arithmetic | statistics | unit",
  "params": {}
}
```

Numbers are strings. Unsupported operations are rejected with HTTP 400.

#### Arithmetic
Request:
```json
{
  "operation": "arithmetic",
  "params": {
    "operator": "add | sub | mul | div",
    "operands": ["1.25", "2.75"],
    "precision": 28
  }
}
```

Response:
```json
{"operation":"arithmetic","result":"4.0"}
```

#### Statistics
Request:
```json
{
  "operation": "statistics",
  "params": {
    "function": "mean | median | variance | stdev | min | max | sum | count",
    "values": ["1", "2", "3", "4"],
    "sample": false,
    "precision": 28
  }
}
```

Response:
```json
{"operation":"statistics","result":"2.5"}
```

#### Unit-safe calculations
Supported units (multiplicative only): `m cm mm km in ft yd mi g kg mg lb s min h day`

Convert:
```json
{
  "operation": "unit",
  "params": {
    "action": "convert",
    "value": "1500",
    "unit": "m",
    "to_unit": "km",
    "precision": 28
  }
}
```

Response:
```json
{"operation":"unit","result":"1.5","unit":"km"}
```

Arithmetic with units:
```json
{
  "operation": "unit",
  "params": {
    "action": "arithmetic",
    "operator": "add",
    "left": {"value":"2.5","unit":"m"},
    "right": {"value":"30","unit":"cm"},
    "result_unit": "m",
    "precision": 28
  }
}
```

Response:
```json
{"operation":"unit","result":"2.8","unit":"m"}
```

Multiplication/division returns base-unit dimensions when no `result_unit`
is provided (for example `m^2` or `m*s^-1`).

## Limits (defaults)
- `MAX_BODY_BYTES=16384`
- `MAX_LIST_ITEMS=1000`
- `MAX_NUMBER_DIGITS=200`
- `MAX_PRECISION=100`
- `DEFAULT_PRECISION=28`
- `REQUEST_TIMEOUT_MS=250`
- `MAX_OUTPUT_CHARS=4096`
