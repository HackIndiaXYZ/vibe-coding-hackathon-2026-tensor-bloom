# Cosign — Team Workstream Prompts

**Purpose:** Cosign is built by a parallel team across four independent workstreams. This document contains four self-contained briefing prompts — one per workstream. Each prompt is **standalone** (an agent or teammate can act on it without reading anything else first, except the documents it points to).

**How to use:** Copy a workstream section below and hand it to the teammate or AI agent assigned to it. Each section is structured the same way:

```
1. Service name + one-line role
2. Required reading (specific PRD + ARCHITECTURE sections)
3. What this service is (context in the larger system)
4. Your scope (what to build)
5. Non-goals (what NOT to build)
6. Interface contracts (how your service talks to the others)
7. Deliverables checklist
8. Definition of done
9. Tech stack
10. Initial setup steps
11. Questions to ask before you commit code
```

---

## Coordination & Synchronization Points

Before workstreams can finish independently, three things must be agreed across the team:

1. **Proto contract** (`libs/proto/*.proto`) — defines the gRPC contract between cosign-api (Go) and cosign-worker (Python). Owned by **Workstream 1 (Go)** initially but reviewed by both. Lock this on Day 1 PM.
2. **REST/SSE API shape** (`libs/ts-types/` generated from Go `apitypes/`) — defines what cosign-web (TS) consumes. Owned by **Workstream 1** with **Workstream 3** as the consumer-of-record. Lock the request/response envelope by Day 2 EOD.
3. **Env-var contract** (`infra/.env.example`) — which env vars each service reads, with example values. Owned by **Workstream 4 (Docker/infra)** but every service workstream contributes the vars it needs. Updated continuously.

**Daily 10-minute sync at 5pm IST** for the team to flag breaking changes to these three contracts.

---

# Workstream 1 — `cosign-api` (Go services)

## Role in one line
**The Go-based HTTP gateway + internal services layer. Handles auth, REST + SSE for the browser, GitHub OAuth + App webhooks, identity/capability registry, reputation scoring, and gRPC orchestration calls to the Python worker.**

## Required reading
Before you commit a single line, read these sections:
- `docs/PRD.md` §1 (Product Vision) + §2 (Problem Statement) — so you know *why* this is being built
- `docs/PRD.md` §6 (Core Feature Set) — the two flows and the HITL gate, so you know what state your endpoints must enable
- `docs/ARCHITECTURE.md` §1 (System Overview) — the 3-service diagram, your place in it
- `docs/ARCHITECTURE.md` §2.1 (cosign-api internal packages) — the exact package layout you're building
- `docs/ARCHITECTURE.md` §3 (Data Flow) — what happens on every request, where your code fits
- `docs/ARCHITECTURE.md` §4 (Database Schema) — your sqlc target
- `docs/ARCHITECTURE.md` §7 (GitHub Integration) — your auth + webhook + fork-mode trigger logic
- `docs/ARCHITECTURE.md` §8 (API Surface) — every endpoint you must serve
- `docs/ARCHITECTURE.md` §9 (Security and Trust) — JWT, HMAC, mTLS, capability gating
- `docs/ARCHITECTURE.md` §11 (Observability) — what to emit on /metrics

## What this service is

`cosign-api` is the **only public-facing service** in the Cosign system. The browser talks to it; the Python worker talks back to it; Postgres + Redis are behind it. It is a **modular monolith**: one Go binary, three internal packages (`gateway`, `identity`, `reputation`) with clean boundaries so any can be extracted later without changing call sites.

In Cosign's product flow:
- A user signs in (you handle the GitHub OAuth dance).
- The user clicks "Review with Cosign" or "Resolve with Cosign" in the web UI.
- The browser POSTs `/goals` to **you**.
- You write the goal to Postgres, call the worker over gRPC, return immediately.
- The browser opens an SSE connection (`GET /stream/goals/{uuid}`) to **you**.
- As the worker runs the agent, it publishes events to a Redis Stream; **you** fan them out to the SSE connection.
- When the agent pauses for a human gate, the worker calls back to **you** with the gate payload; the browser sees it via SSE.
- The user clicks Cosign. The browser POSTs `/goals/{uuid}/resume` to **you**. You record the cosign, write to the audit log, and **post the review/PR on GitHub using the user's OAuth token** (never a bot account), then tell the worker to resume.

## Your scope

Build the `services/cosign-api/` Go service per `ARCHITECTURE.md` §2.1, with all packages and endpoints listed in §8. Specifically:

### Phase 1 — Skeleton & health (start here, all subsequent phases unblock once this is done)
- Go workspace at `services/cosign-api/`, module `github.com/tensor-bloom/cosign/services/cosign-api`
- `cmd/cosign-api/main.go` single binary entrypoint
- `chi` router with middleware: `request_id`, `recovery`, `cors`, `compression`, `slog`-based access log
- `/health` endpoint returning JSON `{ "status": "ok", "version": "...", "commit": "..." }`
- Env-var config loaded via `envconfig` or `viper` from `.env`
- Postgres pool via `pgx` v5, Redis client via `go-redis` v9
- sqlc set up against `migrations/` (sqlc.yaml committed)
- `Dockerfile` (multi-stage: distroless or alpine final)

### Phase 2 — Auth
- `GET /auth/github/login` → redirect to GitHub OAuth (scopes `read:user`, `public_repo`)
- `GET /auth/github/callback` → exchange code, upsert into `users` table, set HttpOnly + SameSite=Lax JWT cookie (RS256, 24h)
- `GET /auth/github/install` → redirect to GitHub App install URL
- `POST /auth/logout` → invalidate session
- `GET /auth/me` → return current user
- JWT middleware (RS256, RSA keypair loaded from env) protecting all non-`/auth/*` and non-`/health` routes
- AES-GCM encrypt/decrypt user OAuth tokens at rest

### Phase 3 — GitHub App webhook receiver (passive inbox feed only)
- `POST /webhooks/github` — verify `X-Hub-Signature-256` with constant-time compare, return 401 on mismatch
- Dispatch: `installation.created/deleted` → maintain `installations` table; `pull_request.opened` / `issues.opened` → INSERT into `inbox_items`
- **Do NOT trigger any agent runs.** Webhooks are inbox-only. See PRD §1.2 point 4.

### Phase 4 — Goals API + gRPC to worker
- `POST /goals` — validate, resolve target repo, INSERT into `goals`, INSERT audit_log, call worker gRPC `SubmitGoal(goal_id)`, return 202 with the goal UUID
- `GET /goals` — paginated list, filterable by status / repo / user
- `GET /goals/{uuid}` — goal detail with tasks, interrupts, critic_iterations, cost_breakdown
- `POST /goals/{uuid}/resume` — write decision + edited_review to `interrupts`, if Flow A also POST the review on GitHub via user's OAuth, call worker gRPC `ResumeFromInterrupt`
- `DELETE /goals/{uuid}` — cancel a running goal
- `GET /goals/{uuid}/audit` — download audit JSON
- `GET /goals/{uuid}/transcript` — export Flow B transcript JSON

### Phase 5 — SSE multiplexer
- `GET /stream/goals/{uuid}` — subscribe to Redis stream `stream:goal:{goal_id}`, forward each event as an SSE `event: ...\ndata: {...}\n\n` chunk
- Support `Last-Event-ID` header for reconnect (replay missed events from the stream)
- Heartbeat every 15s (empty comment line) to keep proxies happy
- `GET /stream/inbox` — subscribe to per-user inbox stream

### Phase 6 — Identity gRPC server (for the worker to call)
- gRPC server on port 50051 implementing `IdentityService`:
  - `VerifyCapability(agent_id, tool_name)` → boolean + reason
  - `GetAgentInfo(agent_id)` → agent + capabilities
  - `RegisterAgent(...)` → new agent
  - `GetUserOAuthToken(user_id)` → AES-GCM-decrypts and returns user OAuth token (used by worker to act as the user on GitHub)

### Phase 7 — Reputation (light)
- Background ticker (every 10 min) computes composite score per agent, updates `reputation` table + Redis `leaderboard:global` ZSET
- `GET /reputation/leaderboard?limit=N` — top-N from Redis
- `GET /reputation/agents/{uuid}` — score + component breakdown
- "Verified Run" badge after 5 consecutive successful goals → INSERT into `badges`

### Phase 8 — Observability + audit
- `/metrics` Prometheus exposition: `cosign_api_http_request_duration_seconds`, `cosign_api_sse_connections_active`, `cosign_api_grpc_calls_total`
- Audit log writes on every state-changing operation
- `GET /audit` + `GET /audit/export` (filterable, JSONL export)

## Non-goals

You are explicitly NOT responsible for:
- Running LLM calls. The worker does that.
- Running agents. The worker does that.
- Talking to Docker / managing sandboxes. The worker does that.
- Rendering any HTML / UI. The frontend does that.
- Polling GitHub. The worker does that via its `tools.github`.
- Anything in `services/cosign-worker/` or `services/cosign-web/`.

If a task feels like "I should call the LLM directly from Go" — stop, that's a signal you're crossing a boundary. The flow is always: browser → cosign-api → cosign-worker (over gRPC) → LLM.

## Interface contracts

### Inbound (REST/SSE from browser)
- See ARCHITECTURE §8 for full endpoint surface and response envelope.
- Response envelope: `{ "data": {...}, "meta": {"request_id":"...", "timestamp":"..."}, "error": null|{} }`
- Error format: `{ "code": "GOAL_NOT_FOUND", "message": "...", "details": {} }`
- SSE event format: `event: <type>\ndata: <json>\nid: <stream-entry-id>\n\n`

### Outbound (gRPC to cosign-worker)
- Proto file: `libs/proto/orchestration.proto`. You own this proto.
- RPCs you call: `SubmitGoal(goal_id)`, `ResumeFromInterrupt(goal_id, decision)`, `CancelGoal(goal_id)`
- Worker is on `WORKER_GRPC_ADDR` (env). Default `cosign-worker:50052` in compose.

### Inbound (gRPC from cosign-worker)
- Same proto file. RPCs the worker calls: `VerifyCapability`, `GetAgentInfo`, `GetUserOAuthToken`, `EmitAuditLog`
- Your gRPC server on `API_GRPC_LISTEN_ADDR` (env). Default `:50051`.

### Postgres
- sqlc-generated queries in `internal/store/`. Migrations in `infra/postgres/migrations/`.
- Tables you own: `users`, `installations`, `repositories`, `agents`, `goals`, `tasks`, `task_dependencies`, `interrupts`, `audit_log`, `reputation`, `badges`, `inbox_items`
- Tables the worker also writes to: `tasks`, `messages`, `critic_iterations`. **Coordinate on schema** — never alter these without telling Workstream 2.

### Redis
- Streams the worker publishes (you consume for SSE fan-out): `stream:goal:{goal_id}`, `stream:agent:{agent_id}`
- Caches the worker uses (you don't touch): `llm:exact:*`, `tool:*`, `plan:*`, `github:etag:*`
- Caches you use: `session:*`, `ratelimit:*`, `leaderboard:global` (ZSET)

## Deliverables checklist

- [ ] Service builds clean (`go build ./...`)
- [ ] `go vet ./...` clean
- [ ] `golangci-lint run` clean
- [ ] All endpoints in ARCHITECTURE §8 implemented and return the envelope shape
- [ ] sqlc generates clean against migrations
- [ ] `/health` returns 200 with `{status, version, commit}`
- [ ] `/metrics` exports all the counters listed above
- [ ] Integration test: full OAuth login → install App → POST /goals → SSE stream connects → POST /goals/{uuid}/resume → review actually posts on a test GitHub PR (under the user's identity)
- [ ] Dockerfile produces an image ≤ 30 MB

## Definition of done

You are done when:
1. The Python worker can call your gRPC server, get a user's OAuth token, and use it to clone a repo.
2. The frontend can sign a user in, POST a goal, open an SSE stream, see events, POST a resume, and see the goal complete — without any errors in your service logs.
3. A test PR review posted via the `/goals/{uuid}/resume` flow shows up on GitHub authored by the signed-in user (not a bot account).
4. `docker compose up` brings up your service alongside Postgres + Redis and `curl localhost:8080/health` returns 200.

## Tech stack

- Go 1.23
- chi v5 (router)
- pgx v5 + sqlc (DB)
- go-redis v9 (Redis)
- grpc-go + protoc-gen-go (gRPC)
- jsonwebtoken-go (JWT)
- golang-jwt/jwt v5 (JWT)
- google/go-github v66 (GitHub API)
- slog (logging)
- prometheus/client_golang (metrics)
- envconfig or viper (config)

## Initial setup steps (suggested order)

1. Scaffold `services/cosign-api/` with `go mod init`.
2. Add chi + slog + envconfig + pgx + go-redis to `go.mod`.
3. Write minimal `main.go` with `/health` and `docker compose up postgres redis` test.
4. Set up `libs/proto/orchestration.proto` and `buf.yaml` for proto generation.
5. Generate sqlc skeleton against ARCHITECTURE §4 schema.
6. Build out auth flow against a real GitHub App (you'll need a teammate to register one — see Workstream 4 for `.env` shape).
7. Iterate through Phases 4–8 in order.

## Questions to ask before you commit code

- Does your endpoint return the standard envelope shape? Errors get `error.code` + `error.message`?
- If your code makes a GitHub write call, are you using the **user's OAuth token** (decrypted from `users` row) or the App's installation token? Writes must use the user's token. Reads can use either.
- If your code creates a goal, did you call worker gRPC `SubmitGoal` after the DB insert?
- If your code resumes a goal (cosign), did you post the review on GitHub *before* calling worker gRPC `ResumeFromInterrupt`? (Order matters — if the review post fails, the worker shouldn't resume.)
- If you're adding a new DB column to a shared table (`tasks`, `messages`, `critic_iterations`), did you tell Workstream 2 in the daily sync?

---

# Workstream 2 — `cosign-worker` (Python services)

## Role in one line
**The Python-based worker running LangGraph multi-agent orchestration, all agent roles (implementer/reviewer/critic), all tools (github/code/file_ops/test_runner/lint/repo_map/review/diff_analysis/search), the SandboxDriver, and the multi-layer cache + per-role LLM router. It is the only service that calls LLMs.**

## Required reading
- `docs/PRD.md` §1 (Vision) + §6 (Core Feature Set) — what you implement
- `docs/PRD.md` §6.8 (Cost Optimization) — caching + per-role routing as a selling point
- `docs/ARCHITECTURE.md` §1 (System Overview) — your place in the system
- `docs/ARCHITECTURE.md` §2.2 (cosign-worker internal packages) — exact package layout
- `docs/ARCHITECTURE.md` §3 (Data Flow) — sequence diagrams for Flow A and Flow B
- `docs/ARCHITECTURE.md` §4 (Database Schema) — which tables you write (tasks, messages, critic_iterations)
- `docs/ARCHITECTURE.md` §5 (Cost Optimization — Caching + Per-Role LLM Routing) — THE central spec for your LLM call path
- `docs/ARCHITECTURE.md` §5.7 (Per-Role LLM Routing) — the YAML config + `LLMRouter` class you must build
- `docs/ARCHITECTURE.md` §6 (Sandbox Architecture) — `SandboxDriver` protocol + DockerDriver implementation
- `docs/ARCHITECTURE.md` §7 (GitHub Integration) — fork-mode logic
- `docs/ARCHITECTURE.md` §9 (Security and Trust) — sandbox isolation, capability gating

## What this service is

`cosign-worker` is **the brain of the system**. It receives goals from `cosign-api` over gRPC, runs LangGraph state machines that orchestrate multiple AI agents working in concert (Flow A: reviewer; Flow B: implementer + critic loop), and acts on GitHub *using the invoking user's OAuth token* (never a bot).

Concretely, when a goal comes in:
1. You receive `SubmitGoal(goal_id)` over gRPC.
2. You load the goal from Postgres and the user's OAuth token from cosign-api's identity service.
3. You build the LangGraph `StateGraph` and start a thread (checkpoint backed by Postgres).
4. The graph runs nodes: `plan_node` → `reviewer` (Flow A) or `critic_loop_subgraph` (Flow B) → `finalize_node`.
5. Each node calls `LLMRouter.acall(role="...", ...)` — never `litellm.acompletion()` directly. The router enforces per-role model selection.
6. Tools (`github_ops`, `code_exec`, etc.) are called from inside nodes. Each tool call passes through capability check + Redis cache before hitting its target.
7. Sandbox execution (clone repo, run tests, write files, push commit) goes through `SandboxDriver`. The v1 implementation `DockerDriver` spawns ephemeral Docker containers with strict resource + network limits.
8. At HITL gates: you write the interrupt to Postgres, publish `gate.pending` to Redis Stream (so cosign-api can fan it out via SSE), call `graph.interrupt()`. When cosign-api resumes you, you continue the graph with `Command(resume=...)`.
9. At finalize: you push branch + open PR using the user's OAuth token (fork-mode aware).

Every LLM call records `tokens_in`, `tokens_out`, `cached_tokens`, `cost_usd` to the `messages` table. This is the source data for the cost dashboard.

## Your scope

Build the `services/cosign-worker/` Python service per ARCHITECTURE §2.2.

### Phase 1 — Skeleton
- `pyproject.toml` (uv project)
- `cosign_worker/__main__.py` — FastAPI app on `:8001` (for `/health`, `/metrics`) + gRPC server on `:50052`
- `/health` endpoint
- asyncpg pool to Postgres, redis-py async client
- gRPC server skeleton implementing `OrchestrationService` (stubs that return `Unimplemented`)
- Dockerfile (Python 3.12-slim base)

### Phase 2 — Sandbox
- `cosign_worker/sandbox/driver.py` — `SandboxDriver` Protocol per ARCH §6.1
- `cosign_worker/sandbox/docker_driver.py` — implementation using `aiodocker`
  - Resource limits: `--memory=2g --cpus=2 --pids-limit=512`
  - Network: dedicated Docker network `cosign_sandbox_net` with egress whitelist (github.com, npm/pypi)
  - Filesystem: read-only root + tmpfs /tmp + bind-mount workspace
  - GIT_ASKPASS helper for token-based auth without writing tokens to disk
  - Janitor: reap containers >30 min old
- Image `cosign/sandbox:latest` built from `infra/sandbox.Dockerfile` (git, node, python, bash, curl)

### Phase 3 — LLM router (cost-optimization core)
- `cosign_worker/llm/router.py` — `LLMRouter` class per ARCH §5.7
- Loads `config/llm-routing.yaml` at startup
- `acall(role=..., tool=..., messages=..., **kw)` resolves to a `(provider, model, api_key_env, fallback_chain)` triple
- Health tracking in Redis: `llm:provider:{name}:errors`, `llm:provider:{name}:ratelimit`
- Defaults to ship: plan_node → Claude Haiku 4.5; critic → Groq Llama 3.3 70B; implementer/reviewer → Claude Sonnet 4.6; diff_analysis → Haiku; repo_map/lint/test_runner → `provider: none`
- `provider: none` is a valid value — those tools execute deterministic local code, no LLM call.
- Every call records to `messages` table with cost

### Phase 4 — Multi-layer cache
- `cosign_worker/llm/prompt_cache.py` — Anthropic `cache_control` wrapper. **Audit every system prompt to ensure static-first / dynamic-last ordering.** Cache breakpoint is critical.
- `cosign_worker/cache/llm_exact.py` — Redis exact-hash cache (24h TTL, temperature-bucketed)
- `cosign_worker/cache/tool_output.py` — per-tool TTLs; `BaseTool.cacheable: bool` opt-in
- `cosign_worker/cache/plan.py` — 12h TTL keyed on normalized goal description
- `cosign_worker/tools/github.py` ETag wrapper — send `If-None-Match`, accept 304 as a hit

### Phase 5 — Tools
Each tool inherits `BaseTool` which provides: capability check (gRPC to identity service) + cache lookup + execution + cache write + audit log emit.

- `cosign_worker/tools/github.py` — `github_ops` (read PRs/issues/files), `github_pr` (post review, open PR, fork repo), `wait_webhook` (Flow B steering). **Uses user's OAuth token passed in via state.**
- `cosign_worker/tools/code.py` — `code_exec` (via SandboxDriver.exec)
- `cosign_worker/tools/file_ops.py` — read/write/delete via SandboxDriver
- `cosign_worker/tools/test_runner.py` — detect repo's test command (pytest/jest/go test/cargo test/Makefile), run, parse results
- `cosign_worker/tools/lint.py` — detect repo's linter (eslint/ruff/gofmt/prettier), run, parse violations
- `cosign_worker/tools/repo_map.py` — tree-sitter-based directory tree + per-file symbol map (no LLM call)
- `cosign_worker/tools/review.py` — composes structured review draft (used by reviewer agent only)
- `cosign_worker/tools/diff_analysis.py` — per-hunk classification + dangerous-pattern detection
- `cosign_worker/tools/search.py` — Brave/Serper API, 1h Redis cache

### Phase 6 — LangGraph orchestration
- `cosign_worker/orchestration/state.py` — `AgentState` TypedDict including `goal_id`, `user_oauth_token`, `tasks`, `tool_results`, `pending_interrupt`, `messages` (Annotated with add_messages), `current_round`, `critic_iterations`
- `cosign_worker/orchestration/checkpoint.py` — `AsyncPostgresSaver` wiring
- `cosign_worker/orchestration/nodes/plan.py` — plan_node calls `router.acall(role="plan_node", ...)` and emits DAG
- `cosign_worker/orchestration/nodes/implementer.py` — emits diff + `self_satisfaction` score
- `cosign_worker/orchestration/nodes/reviewer.py` — Flow A; composes structured review draft via `tools.review`
- `cosign_worker/orchestration/nodes/critic.py` — Flow B; uses Groq for speed
- `cosign_worker/orchestration/nodes/critic_loop.py` — subgraph: implementer ↔ critic until self-satisfaction OR max-iter. Writes to `critic_iterations` table per round. Publishes SSE events per round.
- `cosign_worker/orchestration/nodes/finalize.py` — pushes branch + opens PR via user's OAuth (fork-mode aware)
- `cosign_worker/orchestration/interrupts.py` — HITL gate helpers wrapping `graph.interrupt()`
- `cosign_worker/orchestration/graph.py` — builds the full StateGraph

### Phase 7 — gRPC server
- `cosign_worker/rpc/server.py` implementing `OrchestrationService`:
  - `SubmitGoal(goal_id)` — load goal, start LangGraph thread, return immediately
  - `ResumeFromInterrupt(goal_id, decision, feedback?)` — `graph.Command(resume=...)`
  - `CancelGoal(goal_id)` — mark cancelled, cleanup
- Identity gRPC **client** (calls cosign-api for `VerifyCapability`, `GetUserOAuthToken`, `EmitAuditLog`)

### Phase 8 — Cost surfacing
- Every LLM call writes `messages.cost_usd` via LiteLLM's `completion_cost` helper
- `/metrics` exports: `cosign_worker_goal_cost_usd_sum{role}`, `cosign_worker_cache_hits_total{cache}`, `cosign_worker_llm_tokens_total{provider,model,direction,cached}`, `cosign_worker_critic_iterations` histogram, `cosign_worker_goals_active`, `cosign_worker_sandbox_active`

## Non-goals

You are explicitly NOT responsible for:
- Serving any HTTP to the browser (except `/health`, `/metrics`). All UI-facing traffic goes through cosign-api.
- Auth or JWT handling. cosign-api does that.
- Receiving GitHub webhooks. cosign-api does that.
- Posting PR reviews/comments **on the cosign-api side**. That happens in cosign-api's `/goals/{uuid}/resume` handler after the human cosign. **You** only post during finalize (e.g., when the implementer opens the resulting PR).
- Rendering any UI.
- Writing any non-`tasks`/`messages`/`critic_iterations`/`audit_log`(via gRPC) tables.

## Interface contracts

### Inbound (gRPC from cosign-api)
- Proto file: `libs/proto/orchestration.proto` (owned by Workstream 1).
- RPCs you implement: `SubmitGoal`, `ResumeFromInterrupt`, `CancelGoal`
- Your gRPC server on `WORKER_GRPC_LISTEN_ADDR` (env). Default `:50052`.

### Outbound (gRPC to cosign-api)
- Same proto file.
- RPCs you call: `VerifyCapability(agent_id, tool_name)` on every tool call. `GetAgentInfo(agent_id)`. `GetUserOAuthToken(user_id)` at goal start. `EmitAuditLog(...)` on tool calls + state changes.
- API gRPC on `API_GRPC_ADDR` (env). Default `cosign-api:50051`.

### Outbound (GitHub, LLM providers)
- GitHub: always use the user's OAuth token passed via state. Never the App token (cosign-api may pass an App token separately for read-side optimizations on installed repos; treat as a separate field).
- LLM providers (Anthropic / Groq / OpenAI): always via `LLMRouter`. **Never call LiteLLM directly from outside `llm/router.py`.**

### Postgres
- Tables you write: `tasks`, `messages`, `critic_iterations`. Tables cosign-api writes: everything else. **Coordinate on schema** changes via the daily sync.
- LangGraph's own tables (`checkpoints`, `checkpoint_writes`, `checkpoint_blobs`) are managed by `AsyncPostgresSaver.setup()`.

### Redis
- Streams you publish (cosign-api consumes for SSE): `stream:goal:{goal_id}` (events: `task.started`, `task.tool_call`, `task.completed`, `iteration.implementer`, `iteration.critic`, `gate.pending`, `goal.completed`, etc.)
- Caches you own: `llm:exact:*`, `tool:*`, `plan:*`, `github:etag:*`, `llm:provider:*` health

### Docker socket
- DockerDriver requires read+write access to `/var/run/docker.sock` in compose. Workstream 4 will set the bind mount.

## Deliverables checklist

- [ ] `uv sync` resolves cleanly
- [ ] `ruff check .` + `ruff format --check .` clean
- [ ] `mypy .` clean
- [ ] All nodes + tools + sandbox driver implemented per ARCHITECTURE
- [ ] LLMRouter loads `config/llm-routing.yaml` and routes by role
- [ ] Every system prompt has been audited for static-first / dynamic-last ordering
- [ ] Cache hit visible in `cosign_worker_cache_hits_total` after a second identical goal
- [ ] Critic loop converges (or hits max-iter) and produces a transcript stored in `critic_iterations`
- [ ] PR opens on GitHub **authored by the invoking user** (manually verified)
- [ ] Dockerfile builds an image ≤ 1 GB

## Definition of done

You are done when:
1. cosign-api can call `SubmitGoal` and a goal runs to completion: agent runs in a Docker sandbox, makes LLM calls, writes per-round critic_iterations, publishes events to Redis, pauses at gate.
2. cosign-api can call `ResumeFromInterrupt` and the worker continues, opens a PR on GitHub authored by the user, marks the goal done.
3. Running the same Flow B goal twice shows ≥50% cache hit rate in `/metrics`.
4. With default `config/llm-routing.yaml`, a 3-round Flow B goal costs <$0.10 end-to-end (visible in the goal's cost_breakdown).
5. `docker compose up` brings up your service and the sandbox image is reachable.

## Tech stack

- Python 3.12
- uv (project + dep manager)
- FastAPI + uvicorn (HTTP for /health, /metrics)
- grpcio + grpcio-tools (gRPC)
- LangGraph ≥0.2 + langchain-core ≥0.3 + langgraph-checkpoint-postgres
- LiteLLM ≥1.40 (multi-provider LLM client)
- asyncpg (Postgres)
- redis ≥5 with hiredis (Redis)
- aiodocker (sandbox)
- githubkit (GitHub API)
- structlog (logging)
- prometheus-fastapi-instrumentator (metrics)
- tree-sitter + language packs (repo_map)

## Initial setup steps (suggested order)

1. Scaffold `services/cosign-worker/` with `uv init`.
2. Add deps to `pyproject.toml`; `uv sync`.
3. Write `__main__.py` with FastAPI `/health` and a gRPC server stub.
4. Generate Python proto code from `libs/proto/orchestration.proto`.
5. Build the SandboxDriver + DockerDriver against a real Docker daemon early — this is the highest-risk piece.
6. Build the LLMRouter with `config/llm-routing.yaml` next — it's the foundation every node depends on.
7. Build one node (`plan_node`) end-to-end against the router. Verify cost tracking writes to `messages`.
8. Build the rest of the graph (implementer → reviewer → finalize for Flow A; implementer + critic_loop + finalize for Flow B).
9. Wire HITL gates last.

## Questions to ask before you commit code

- Are you calling `LLMRouter.acall(role="...")` and never `litellm.acompletion()` directly?
- Did this LLM call have its system prompt structured static-first / dynamic-last? Did you mark the cache breakpoint correctly?
- Did this tool call go through `BaseTool` (so capability check + cache wrapper happen)?
- Did you record `cost_usd` to `messages` for this call?
- For GitHub writes: are you using the user's OAuth token from `AgentState.user_oauth_token`, NOT the App token?
- For sandbox operations: did you use `SandboxDriver` methods (so the future k8s driver doesn't break), NOT raw `aiodocker` calls?
- Did you publish the expected SSE event after this state change (so the UI can render)?

---

# Workstream 3 — `cosign-web` (Frontend)

## Role in one line
**The Next.js web app that is the primary entrypoint for users. Renders the dashboard, inbox, goal pages with live SSE event feeds, the inline ReviewEditor (Flow A), the TranscriptViewer (Flow B), the CosignGate modal, the cost dashboard, and the audit log viewer.**

## Required reading
- `docs/PRD.md` §1.2 (the six innovation points) — every UI decision should reinforce these
- `docs/PRD.md` §2.3 (Concrete User Scenarios) — the three user journeys your UI must enable
- `docs/PRD.md` §4 (Personas) + §6 (Core Feature Set) — flow specifications
- `docs/PRD.md` §6.7 (Iteration Transcript) — the transcript is a first-class artifact in the UI
- `docs/PRD.md` §6.8 (Cost Optimization) — the cost numbers visible in the UI
- `docs/ARCHITECTURE.md` §1 (System Overview) — your place
- `docs/ARCHITECTURE.md` §2.3 (cosign-web internal packages) — file structure
- `docs/ARCHITECTURE.md` §3 (Data Flow) — what events you'll consume via SSE for both flows
- `docs/ARCHITECTURE.md` §8 (API Surface) — every endpoint you'll call
- `docs/ROADMAP.md` "Demo Script" — the user journey you must make demo-able

## What this service is

`cosign-web` is the **only thing users see**. It's the surface that makes Cosign feel like a web app (vs a bot or a CLI). Critical UX principles, baked into every decision:

- **User-initiated everywhere.** Every agent run starts with a button click in your UI. There is no `/cosign review` slash command in v1. There is no "agent ran while you weren't looking."
- **The user is always the author.** Reviews appear in the UI as drafts attributable to the user. PR previews show the user's name and avatar. The bot identity is invisible.
- **The transcript is visible.** Flow B's critic loop is rendered live as it runs, per-round, with the implementer's self-satisfaction score visualized as a number/bar.
- **Cost is visible.** Every goal page shows `$/goal` at the top. The `/cost` dashboard makes the cost-savings story tangible.

If you find yourself building a UI that hides what the AI is doing or what each step cost, stop — that's an anti-pattern for this product.

## Your scope

Build `services/cosign-web/` per ARCHITECTURE §2.3.

### Phase 1 — Scaffold + auth
- Next.js 15 App Router with TypeScript + Tailwind + Shadcn-style components
- Typed API client at `lib/api.ts` (types generated from Go `apitypes/` — see `libs/ts-types/`)
- Auth flow: "Sign in with GitHub" button → redirect to cosign-api `/auth/github/login` → callback → land back with cookie set
- `/` (landing/dashboard) renders the signed-in user's avatar + a list of recent goals
- Layout: header with user menu, left rail with nav (Inbox / Reviews / Resolves / Audit / Cost / Compare)

### Phase 2 — Inbox + goal creation
- `/inbox` — shows PRs and issues from the user's connected repos (data from `GET /inbox`). Each item has [Review with Cosign] or [Resolve with Cosign] CTA.
- `/review?pr_url=...` — paste-any-PR-URL form, POSTs to `/goals` and redirects to the goal detail page.
- `/resolve?issue_url=...` — paste-any-issue-URL form, optional steering note textarea, POSTs to `/goals`.

### Phase 3 — Goal detail page + live SSE
- `/goals/[uuid]` — page that:
  - Loads goal detail from `GET /goals/{uuid}` on mount
  - Opens SSE connection to `GET /stream/goals/{uuid}` with `Last-Event-ID` reconnect logic
  - Renders **cost-by-role bar at the top** (`plan $0.003 · critic $0.008 · implementer $0.052 · tools $0.004 = $0.067 total`). Updates live.
  - Renders live event feed (`<EventFeed>` component) — one entry per task.started, task.tool_call, iteration.implementer, iteration.critic, etc.
- `useSSE` hook in `lib/useSSE.ts` with reconnect logic + typed event parsing

### Phase 4 — CosignGate + ReviewEditor (Flow A)
- `<CosignGate>` modal renders when `gate.pending` event arrives via SSE
- For Flow A (type `pr_review_gate`): renders `<ReviewEditor>` — inline-editable text fields per review section:
  - Summary
  - Risk score (visual)
  - Per-file comments (each editable)
  - Asked changes (editable)
  - Praise (editable)
- Actions: [Edit & Cosign] / [Regenerate with note] / [Cancel]
- On cosign: POST `/goals/{uuid}/resume` with `{ decision: "approve", edited_review: {...} }`

### Phase 5 — TranscriptViewer (Flow B)
- `<TranscriptViewer>` — collapsible per-round blocks. Each round shows:
  - Round number + timestamp
  - Implementer's diff (use a diff viewer library — `@git-diff-view/react` or `react-diff-viewer-continued`)
  - Implementer's self-satisfaction score (visual bar 0→1)
  - Critic's structured feedback (blocking_issues / suggestions / score / rationale)
- For Flow B (type `critic_loop_gate`): renders `<TranscriptViewer>` + final diff + actions [Cosign & open PR] / [Revise w/ feedback] / [Cancel]

### Phase 6 — Cost dashboard + audit + compare
- `/cost` — running totals across all goals, cache hit rate chart, cost-mix ratio (cheap models ÷ premium models). Also a "what if everything was Sonnet?" toggle for the demo.
- `/audit` — table with filters (goal, actor, event_type, date range) + JSONL export button
- `/compare` — server-rendered competitive comparison table (data from PRD §5)

### Phase 7 — Polish + responsive
- Goal page works on mobile (cosign gestures need to work over-the-shoulder during demos)
- Keyboard shortcuts at the gate: `a` = approve, `r` = revise, `x` = cancel
- Loading skeletons everywhere there's a network call
- Toast on goal completion / failure

## Non-goals

You are NOT responsible for:
- Calling any LLM. Frontend only consumes API.
- Talking to Docker / sandboxes. Frontend never touches Docker.
- Authenticating to GitHub yourself. cosign-api handles OAuth; you just call its endpoints and trust the session cookie.
- Implementing webhooks. Pure frontend.
- Posting reviews/comments to GitHub yourself. cosign-api does that during `/goals/{uuid}/resume`.

## Interface contracts

### REST consumption (everything via cosign-api)
- Base URL: `NEXT_PUBLIC_API_BASE_URL` (env). Default `http://localhost:8080` in dev.
- Standard envelope: every response is `{ data, meta, error }`.
- Endpoints you call: see ARCHITECTURE §8 — `/goals` POST/GET, `/goals/{uuid}` GET, `/goals/{uuid}/resume` POST, `/inbox` GET, `/audit` GET, `/cost` GET, `/auth/me` GET, `/auth/github/login` and `/auth/github/install` redirects.

### SSE consumption
- `EventSource('/stream/goals/{uuid}')` opens with cookie auth.
- Event types you must handle (see ARCHITECTURE §8.3): `task.started`, `task.tool_call`, `task.completed`, `task.failed`, `iteration.implementer`, `iteration.critic`, `gate.pending`, `gate.resolved`, `goal.completed`, `goal.failed`, `goal.cancelled`, `cost.updated`
- Implement `Last-Event-ID` reconnect — when the connection drops, reopen with the header set to the last event ID seen.

### Type safety
- `libs/ts-types/` contains TypeScript types generated from Go `apitypes/`. Import from there, never define request/response shapes by hand. **If a type is missing, ask Workstream 1 to add it to `apitypes/`; do not patch ts-types directly.**

## Deliverables checklist

- [ ] `pnpm build` (or `npm run build`) succeeds
- [ ] `tsc --noEmit` clean (strict mode on)
- [ ] `eslint .` clean
- [ ] All pages in scope render with mocked + real data
- [ ] SSE auto-reconnects after a 5-second network drop (manual test)
- [ ] CosignGate keyboard shortcuts work
- [ ] Cost-by-role bar renders correct numbers from `GET /goals/{uuid}`
- [ ] Dockerfile produces an image ≤ 200 MB
- [ ] Mobile-responsive: gate modal usable on a 375px-wide viewport

## Definition of done

You are done when:
1. A user signs in with GitHub, pastes a PR URL, clicks Review with Cosign, sees live events stream in, the ReviewEditor opens with a draft, they edit it, click Cosign, and the review appears on the PR on GitHub.
2. A user pastes an issue URL, clicks Resolve with Cosign, sees implementer + critic iterating live with round numbers and scores, the gate appears with the full transcript, they cosign, the PR opens on GitHub.
3. `/cost` page shows running totals and the per-goal cost bar matches what's in the database.
4. The demo script in `ROADMAP.md` runs without UI bugs.

## Tech stack

- Next.js 15 (App Router)
- React 19
- TypeScript 5.6+ (strict)
- Tailwind CSS 4
- Shadcn UI components (Radix primitives)
- TanStack Query for data fetching (over fetch)
- `react-diff-viewer-continued` or `@git-diff-view/react` for diff rendering
- `lucide-react` for icons
- ESLint + Prettier

## Initial setup steps (suggested order)

1. `pnpm dlx create-next-app@latest services/cosign-web --typescript --tailwind --app`.
2. Install Shadcn, TanStack Query.
3. Wire `lib/api.ts` with a typed fetch wrapper that handles the envelope shape.
4. Build the auth flow end-to-end — sign in, land back, see avatar.
5. Build the goal detail page with mocked SSE events first; wire to real SSE later when cosign-api is ready.
6. Build CosignGate + ReviewEditor against mocked data; wire to real flow when cosign-worker is ready.
7. Build TranscriptViewer against mocked transcript data; wire to real critic loop later.
8. Add cost dashboard, audit, compare.
9. Polish.

## Questions to ask before you commit code

- Does this UI element communicate the "user-initiated" or "you are the author" or "transcript is visible" or "cost is visible" message, or does it hide it?
- Is the data flowing through `lib/api.ts` with proper types, or did you slip in `any`?
- Are SSE events being handled by a single hook (`useSSE`), or did you reimplement SSE handling per-component?
- If you added a new request, did you check whether the type exists in `libs/ts-types/`? If not, did you ask Workstream 1?
- Does the page work without errors when there's no data yet (first-time user, no goals)?
- Does the page show a loading skeleton instead of jumping content on data arrival?

---

# Workstream 4 — Docker + Infra (Glue)

## Role in one line
**The Docker Compose + sandbox image + Caddy + setup-dev.sh that ties Workstreams 1–3 into a running system. Owns the env-var contract, the secret management story, and the deploy path to the demo VM.**

## Required reading
- `docs/PRD.md` §1.2 (innovation points) — to understand what the system needs to do
- `docs/ARCHITECTURE.md` §1 (System Overview) — the diagram you're operationalizing
- `docs/ARCHITECTURE.md` §6 (Sandbox Architecture) — sandbox image + network constraints you must enforce
- `docs/ARCHITECTURE.md` §10 (Deployment) — the v1 Compose layout + k8s-readiness rules
- `docs/ARCHITECTURE.md` §11 (Observability) — metrics endpoints to scrape
- `docs/ARCHITECTURE.md` §9 (Security and Trust) — sandbox isolation, secret management
- `docs/ROADMAP.md` Day 1 (scaffolding) and Day 8 (deploy + record demo)

## What this service is

You aren't writing application code. You're writing the **operational glue** that lets the team's three application services come up together, lets a sandbox image run agents in isolation, and lets the demo VM serve a public HTTPS URL on demo day.

You own four artifacts:
1. **`infra/docker-compose.yml`** — single compose file that brings up the whole system locally.
2. **`infra/sandbox.Dockerfile`** — the image agents run inside (git + node + python + bash + curl).
3. **`infra/Caddyfile`** — reverse proxy + auto-TLS for the demo VM.
4. **`scripts/setup-dev.sh`** — one-command bootstrap for new devs (and CI).

You also own the **env-var contract** (`infra/.env.example`) — the single source of truth for what every service expects in its environment. As application services need new env vars, they add them to your `.env.example` (with safe defaults / placeholder values where applicable) so a new dev never wonders "what should I set this to?"

## Your scope

### Phase 1 — `infra/docker-compose.yml`
- Services: `postgres`, `redis`, `cosign-api`, `cosign-worker`, `cosign-web`, `caddy`
- Postgres image: `pgvector/pgvector:pg16` with named volume + healthcheck (`pg_isready`)
- Redis image: `redis:7-alpine` with `--appendonly yes` + named volume + healthcheck (`redis-cli ping`)
- All app services have `depends_on` with `condition: service_healthy` for Postgres and Redis
- Each app service has its own healthcheck against `/health`
- All app services on a shared private network `cosign_internal`
- Sandboxes use a separate network `cosign_sandbox_net` (egress-restricted)
- `cosign-worker` bind-mounts `/var/run/docker.sock:/var/run/docker.sock` (DockerDriver needs this)
- Resource limits per service (CPU + memory) so a runaway test doesn't kill the VM

### Phase 2 — Per-service Dockerfiles
- Multi-stage builds for each app service (build stage + minimal runtime stage)
- `cosign-api`: Go 1.23 build → distroless or alpine runtime; image ≤ 30 MB
- `cosign-worker`: Python 3.12-slim base; uv install; image ≤ 1 GB (most weight is LLM SDK deps)
- `cosign-web`: Next.js build → minimal Node runtime or static export; image ≤ 200 MB
- Non-root user in each runtime stage
- `HEALTHCHECK` directives in each Dockerfile

### Phase 3 — Sandbox image (`infra/sandbox.Dockerfile`)
- Base: `alpine:3` or `debian:slim`
- Tools: `git`, `node` (latest LTS), `python3`, `bash`, `curl`, `make`, `jq`, `ripgrep`, `tree-sitter` CLI
- A non-root user `agent` to run commands as
- A `/workspace` directory owned by `agent`
- `GIT_ASKPASS` helper script that reads the token from an env var so we never write tokens to disk
- Network whitelist enforced by Docker network config (no NetworkPolicy yet — that's k8s)

### Phase 4 — Caddy + TLS
- `infra/Caddyfile` for the demo VM:
  - `cosign.example.dev` → reverse proxy to `cosign-web:3000`
  - `api.cosign.example.dev` → reverse proxy to `cosign-api:8080`
- Auto-TLS via Let's Encrypt
- Sets `X-Forwarded-*` headers
- Caddy data volume for cert persistence

### Phase 5 — `scripts/setup-dev.sh`
- Checks deps: `docker`, `docker compose`, `go`, `uv`, `node`, `pnpm`
- Copies `.env.example` → `.env` if missing (warns user to fill in keys)
- Builds sandbox image: `docker build -f infra/sandbox.Dockerfile -t cosign/sandbox:latest infra/`
- Starts Postgres + Redis: `docker compose up -d postgres redis`
- Waits for healthchecks
- Runs migrations: `docker compose run --rm cosign-api migrate up` (cosign-api ships migration commands)
- Starts the app services
- Prints "Cosign is up at http://localhost:3000"

### Phase 6 — `infra/.env.example`
Single source of truth for env vars. Sections:
```
# === Database ===
POSTGRES_PASSWORD=changeme
DATABASE_URL=postgres://cosign:changeme@postgres:5432/cosign

# === Redis ===
REDIS_URL=redis://redis:6379

# === GitHub App (Workstream 1 owns these — see Phase 2 of WS1) ===
GITHUB_APP_ID=
GITHUB_APP_PRIVATE_KEY_PATH=/run/secrets/github_app_key
GITHUB_WEBHOOK_SECRET=
GITHUB_OAUTH_CLIENT_ID=
GITHUB_OAUTH_CLIENT_SECRET=

# === JWT (Workstream 1) ===
JWT_RSA_PRIVATE_KEY_PATH=/run/secrets/jwt_private
JWT_RSA_PUBLIC_KEY_PATH=/run/secrets/jwt_public

# === User OAuth token encryption (Workstream 1) ===
OAUTH_TOKEN_ENCRYPTION_KEY=  # 32 bytes base64 for AES-GCM

# === LLM providers (Workstream 2 — per-role keys) ===
ANTHROPIC_API_KEY=
ANTHROPIC_CHEAP_API_KEY=  # optional: separate billing for Haiku
GROQ_API_KEY=
OPENAI_API_KEY=

# === Search tools ===
BRAVE_API_KEY=
SERPER_API_KEY=  # alternative

# === Service URLs ===
API_BASE_URL=http://cosign-api:8080
WORKER_GRPC_ADDR=cosign-worker:50052
API_GRPC_ADDR=cosign-api:50051
NEXT_PUBLIC_API_BASE_URL=http://localhost:8080

# === Sandbox driver ===
SANDBOX_DRIVER=docker  # docker | k8s (k8s is post-hackathon)

# === Observability ===
LOG_LEVEL=info
LOG_FORMAT=json
PROMETHEUS_LISTEN_ADDR=:9090
```

### Phase 7 — Demo VM provisioning (Day 8 of ROADMAP)
- `scripts/provision-demo.sh` — provisions a Hetzner CX22 or DO basic droplet, installs Docker, pulls images, brings up compose
- `scripts/deploy-demo.sh` — `docker compose pull && docker compose up -d` with health-check gating
- Domain DNS A-record points to the VM (you flag if DNS is missing on Day 7 evening so it has time to propagate)
- Backup demo URL on `*.nip.io` in case TLS provisioning runs late

## Non-goals

You are NOT responsible for:
- Writing Go, Python, or TypeScript application logic.
- Modifying any service code beyond adding `HEALTHCHECK` directives or build-arg defaults.
- Implementing CI/CD pipelines (post-hackathon).
- Writing Kubernetes manifests (post-hackathon — design rules in ARCHITECTURE §10.2 must be followed by other workstreams; you don't write the manifests).
- Defining metric names or audit log payloads — that's Workstreams 1 and 2.

## Interface contracts

### To other workstreams
- **Env-var contract** (`infra/.env.example`) — when any service needs a new env var, that service's owner adds it to your `.env.example` via PR. You review for: sensible default, no real secret leaked, naming consistency (UPPER_SNAKE).
- **/health endpoint** — every app service must serve `GET /health` returning 200 with `{status:"ok",version,commit}`. You define the schema; service workstreams must match.
- **Container labels** — every app image gets `org.opencontainers.image.{title, version, revision, source}` labels via Dockerfile.
- **Shared volume conventions:** `postgres_data` and `redis_data` are named volumes; never bind-mount Postgres data dirs in dev (causes permissions issues).

### To external systems
- LetsEncrypt for TLS on the demo VM.
- GitHub App webhook URL must be HTTPS — for local dev, document that devs need `cloudflared tunnel` or `ngrok http 8080`.

## Deliverables checklist

- [ ] `./scripts/setup-dev.sh` brings the whole stack up from a clean machine in <5 min (post-image-pull)
- [ ] `docker compose up` succeeds with no errors after `.env` is populated
- [ ] All 6 services pass their healthchecks within 60s of `docker compose up`
- [ ] Sandbox image builds and `cosign-worker` can `docker run cosign/sandbox:latest echo ok`
- [ ] Caddy serves HTTPS on the demo VM with auto-TLS
- [ ] `.env.example` is complete and a new dev with a fresh checkout can fill it in and run
- [ ] No secrets committed to git (verify with `git secrets --scan`)
- [ ] `docker compose down -v` cleans up everything

## Definition of done

You are done when:
1. A new developer can `git clone`, run `./scripts/setup-dev.sh`, fill in 3–4 keys in `.env`, and have Cosign running locally at `http://localhost:3000`.
2. The demo VM at `cosign-demo.{domain}` serves HTTPS and runs the same compose stack.
3. Sandboxes spawned by `cosign-worker` are network-isolated (cannot reach `cosign-api` or `cosign-worker` from inside).
4. No secret material lives in any image layer or in the compose file.

## Tech stack

- Docker + Docker Compose v2
- Caddy 2 (reverse proxy + auto-TLS)
- bash (for scripts)
- pgvector/pgvector:pg16
- redis:7-alpine

## Initial setup steps (suggested order)

1. Stand up Postgres + Redis only in compose; verify healthchecks pass.
2. Add cosign-api skeleton service to compose (Workstream 1 provides a Dockerfile early); verify it can connect to Postgres.
3. Add cosign-worker similarly.
4. Add cosign-web similarly.
5. Build the sandbox image and verify cosign-worker can spawn a container.
6. Set up Caddy for local TLS (use `tls internal` for local) so the OAuth callback URL works.
7. Maintain `.env.example` as other workstreams report new vars.
8. Late Day 7 / Day 8: provision the demo VM.

## Questions to ask before you commit code

- Is this secret? If yes, is it in `.env.example` as a placeholder (NOT a real value)?
- Does this service have a `/health` endpoint configured in its `healthcheck`?
- If a service needs a new bind mount or env var, did you tell the owning workstream?
- Does this image have a non-root user as the final `USER`?
- Are you running services on the `cosign_internal` network (not the default Docker bridge, which has implicit DNS exposure)?
- Are sandboxes on `cosign_sandbox_net` with egress whitelisting, not on the internal network?

---

# Appendix — Cross-Workstream Decision Log

Things that must be agreed and recorded as the team works. Each workstream owner updates this section when they make a decision that affects another workstream.

| Date | Decision | Owner | Affects | Notes |
|---|---|---|---|---|
| 2026-06-02 | Proto file structure: single `orchestration.proto` covers worker RPCs + identity RPCs | WS1 | WS1, WS2 | One file for v1; split if it grows past ~400 lines |
| 2026-06-02 | TS types generated from Go `apitypes` (not OpenAPI) | WS1 | WS1, WS3 | Use `tygo` or similar Go→TS code generator |
| 2026-06-02 | `provider: none` is a valid value in `llm-routing.yaml` for tools that don't call LLMs | WS2 | WS2 | Skips LLMRouter entirely; tool runs deterministic local code |
| 2026-06-02 | Sandbox containers spawned via DockerDriver, NOT docker-compose | WS2, WS4 | WS2, WS4 | Compose only defines the long-running services; sandboxes are runtime-spawned |
| | | | | |

---

*This document is the single source of truth for "who builds what" on Cosign. Time-based delivery dates + cut lines + the demo script live in [ROADMAP.md](./ROADMAP.md). Product scope lives in [PRD.md](./PRD.md). Technical detail lives in [ARCHITECTURE.md](./ARCHITECTURE.md).*
