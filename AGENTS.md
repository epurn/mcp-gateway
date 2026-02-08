# MCP Gateway — Agent Instructions (Binding)

You are an expert software engineer working on the MCP Gateway project.
These instructions are binding and must be followed throughout the session.

See [.agent/rules/rules.md](.agent/rules/rules.md) for detailed technical constraints and standards.

---

## Project Intent

Build a **thin, offline-safe MCP Gateway** that acts as the **single MCP ingress**
for internal LLM-powered tools (chat apps, VS Code + Continue).

The gateway is intentionally minimal and demo-focused.
It is NOT a platform, control plane, or agent framework.

---

## Tool Architecture (Important)

Tools are **modular components** and are **not implemented inside the gateway**.

- Each tool is deployed as its **own Docker image**
- Tools run as **separate containers or services**
- The gateway **never executes tools directly**
- The gateway’s role is limited to:
  - scoped tool exposure via MCP `tools/list` on endpoint-specific routes
  - auth and policy enforcement
  - request validation
  - routing `tools/call` requests to tool backends
  - returning responses and artifacts

The Docker image is the **unit of deployment** for tools.
The gateway must remain small and free of tool-specific logic.

---

## Core Goals

- Prevent accidental data leakage
- Support multiple concurrent users
- Operate fully offline / airgapped
- Be containerized (Docker / Compose only)
- Demonstrate clear value to:
  - Engineers
  - Analysts
  - Non-technical stakeholders

Target delivery: **1–2 weeks**.

---

## Locked Architecture (Do Not Change)

- Single MCP ingress front door (Nginx) with scoped MCP endpoints
- Scoped endpoint model:
  - `/calculator/sse`
  - `/git/sse`
  - `/docs/sse`
- Tool exposure filtered by endpoint scope + user tool permissions
- Thin routing layer to external tool containers
- No local executor
- No internet tools by default
- Read-only or propose-only tools only (v1)
- Hard break:
  - no unified `/sse`
  - no `/messages`
  - no `find_tools` / `call_tool`

---

## Explicit Non-Goals (Reject If Suggested)

- No arbitrary shell execution in the gateway
- No browsing the gateway host filesystem
- No SaaS integrations (Jira, Slack, etc.)
- No write-back automation
- No endpoint or device lockdown logic
- No UI beyond logs and health checks
- No Kubernetes requirement
- No “AI agent autonomy”

If a change violates any of the above, reject it and explain why.

---

## Locked v1 Tool Set (Do Not Expand)

Exactly **three tools** may exist in v1:

1. **Git (Read-Only Intelligence)**
   - History, diff, blame, search
   - Read-only repo mirrors
   - No write operations

2. **Exact Computation / Calculator**
   - Deterministic, high-precision math
   - Statistics and unit-safe calculations
   - No side effects

3. **Document / Report Generation**
   - Deterministic PDF / DOCX generation
   - Downloadable artifacts
   - Backed by Pandoc or equivalent

No additional tools may be added in v1.

---

## Design Priorities (In Order)

1. Safety / least privilege
2. Determinism and reproducibility
3. Simplicity (minimal diffs over rewrites)
4. Auditability
5. Demo clarity
6. Extensibility **only** if it adds near-zero complexity

---

## Implementation Rules

- Fail closed on auth and policy checks
- Validate all tool inputs via explicit schemas
- Enforce timeouts and output size limits on every routed tool call
- Emit structured audit logs for **every** tool invocation
  - Include user, tool name, decision, and metadata
- Syncing tool registry from `config/tools.yaml` must deactivate tools not present (do not delete history)
- Tools must be stateless in v1
- Avoid adding background workers or async queues unless strictly required

---

## Working Style

- Be concise and technical
- Prefer concrete code over discussion
- Avoid speculative architecture
- Call out risks explicitly
- If something is “good enough for v1”, leave it alone
- Always rerun tests after making changes

---

## MCP Client Integration Rules (v2 Dev)

- Prefer `node scripts/mcp_http_bridge.js` for stdio MCP client integration in this repo
- For VS Code workspace config, use `.vscode/mcp.json` with top-level `servers` (not `mcpServers`)
- Prefer bridge args that auto-issue dev JWTs from `http://localhost:8010/token`; do not hardcode long-lived tokens in docs
- Treat `docker/docker-compose.auth-test.yml` + `services/jwt_issuer` as development-only auth test infrastructure
- Remove temporary debug/test helpers after validation unless they provide clear ongoing value
- Use scoped endpoints directly:
  - calculator work via `/calculator/sse`
  - git read-only work via `/git/sse`
  - document generation via `/docs/sse`
  Use direct/non-MCP alternatives only if MCP tools are unavailable or the user explicitly asks.

---

## If Unsure

When in doubt, prefer:
- fewer features
- smaller surface area
- safer defaults
- clearer demo behavior

## Commenting Guidelines (Binding)

Comments must be **intentional, sparse, and high-signal**.

Use comments only to:
- Explain *why* a non-obvious decision exists
- Document security, safety, or policy constraints
- Clarify interfaces, contracts, or invariants
- Warn against incorrect or dangerous usage

Do NOT use comments to:
- Restate what the code obviously does
- Narrate control flow line-by-line
- Explain basic language features
- Add TODOs without clear ownership or rationale

Guidelines:
- Prefer self-documenting code over comments
- Comments should explain **intent**, not **implementation**
- If a comment becomes outdated, delete or update it immediately
- Avoid block comments inside functions unless strictly necessary
- Use docstrings only for public APIs or externally consumed interfaces

When in doubt:
- Remove the comment
- Or refactor the code to make the comment unnecessary
