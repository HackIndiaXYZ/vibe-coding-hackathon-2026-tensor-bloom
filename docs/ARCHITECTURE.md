# Cosign — Architecture

**Version:** 0.1.0-draft
**Last Updated:** 2026-06-02
**Companion docs:** [PRD.md](./PRD.md) · [ROADMAP.md](./ROADMAP.md)

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Internal Module Boundaries](#2-internal-module-boundaries)
3. [Data Flow](#3-data-flow)
4. [Database Schema](#4-database-schema)
5. [Caching](#5-caching)
6. [Sandbox Architecture](#6-sandbox-architecture)
7. [GitHub Integration](#7-github-integration)
8. [API Surface](#8-api-surface)
9. [Security and Trust](#9-security-and-trust)
10. [Deployment](#10-deployment)
11. [Observability](#11-observability)

---

## 1. System Overview

Cosign is a **3-service modular monolith**: each service is one binary, but each binary contains multiple internal packages with clean boundaries so any package can be extracted into its own service later without changing call sites.

```
                      Browser (HTTPS + SSE + WSS)
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  cosign-api  (Go 1.23 · chi · go-redis · sqlc · grpc-go)         │
│                                                                  │
│   ┌──────────┐   ┌───────────┐   ┌─────────────┐                 │
│   │ gateway  │   │ identity  │   │ reputation  │                 │
│   │  HTTP    │   │  agents   │   │  scoring    │                 │
│   │  JWT     │   │  users    │   │  leaderbd   │                 │
│   │  SSE     │   │  caps     │   │  badges     │                 │
│   │  webhook │   │           │   │             │                 │
│   └──────────┘   └───────────┘   └─────────────┘                 │
└──────────────────────────────┬───────────────────────────────────┘
                               │ gRPC (orchestration RPC)
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  cosign-worker  (Python 3.12 · FastAPI · LangGraph · uv)         │
│                                                                  │
│   ┌──────────────┐  ┌──────────────────────────────────────┐     │
│   │ orchestration│  │ tools                                │     │
│   │              │  │  ├─ tools.github (acts as user OAuth)│     │
│   │ StateGraph:  │  │  ├─ tools.code   (uses SandboxDriver)│     │
│   │  implementer │  │  ├─ tools.file_ops                   │     │
│   │  reviewer    │  │  ├─ tools.test_runner                │     │
│   │  critic loop │  │  ├─ tools.lint                       │     │
│   │  HITL gates  │  │  ├─ tools.repo_map (tree-sitter)     │     │
│   │  checkpoint  │  │  ├─ tools.review (structured)        │     │
│   │              │  │  ├─ tools.diff_analysis              │     │
│   │              │  │  └─ tools.search                     │     │
│   │              │  │                                      │     │
│   │              │  │ SandboxDriver protocol               │     │
│   │              │  │  └─ DockerDriver (v1)                │     │
│   │              │  │     (KubernetesDriver post-hackathon)│     │
│   └──────────────┘  └──────────────────────────────────────┘     │
└──────────────────────────────┬───────────────────────────────────┘
                               │
            ┌──────────────────┴──────────────────┐
            ▼                                     ▼
┌────────────────────────┐           ┌─────────────────────────────┐
│  PostgreSQL 16         │           │  Redis 7                    │
│  + pgvector (deferred) │           │  - String / Hash caches     │
│  sqlc (Go) + asyncpg   │           │  - Streams (SSE pub/sub)    │
│  (Python)              │           │  - SortedSet (leaderboard)  │
└────────────────────────┘           └─────────────────────────────┘

           cosign-web (Next.js 15 App Router · React 19 · Tailwind)
           Served separately on port 3000 in dev; static export
           to api/static or own subdomain in prod.
```

### 1.1 Service-to-service protocols

| Edge | Protocol | Why |
|---|---|---|
| Browser ↔ cosign-api | HTTPS + SSE (+ WSS later) | SSE = Server-Sent Events. See §1.2 below for why SSE and not WebSockets. |
| cosign-api ↔ cosign-worker | gRPC (HTTP/2) | Typed contracts, bidirectional streaming for orchestration events back to api, fast (~1ms p50 over localhost) |
| cosign-api ↔ Postgres | TCP (sqlc-generated queries) | Compile-time-safe SQL in Go via sqlc |
| cosign-worker ↔ Postgres | TCP (asyncpg) | LangGraph `AsyncPostgresSaver` uses asyncpg; tool servers share the pool |
| Both services ↔ Redis | TCP (go-redis / redis-py) | Caches, Streams, SortedSet |
| cosign-worker ↔ sandbox containers | Docker SDK (HTTP + Unix socket) | The "DockerDriver" — see §1.3 for what a *driver* means here, full detail in §6. |
| cosign-worker ↔ LLM providers | HTTPS | Anthropic / Groq / OpenAI via LiteLLM router |
| cosign-worker ↔ GitHub | HTTPS | `githubkit` (Python). All calls use the **invoking user's OAuth token**, never a bot token. |

### 1.2 SSE — what it is and how Cosign uses it

**Server-Sent Events (SSE)** is a one-way streaming protocol built on top of HTTP. The client opens a long-lived `GET` request with `Accept: text/event-stream`; the server keeps the connection open and writes newline-delimited event chunks as state changes. The browser exposes this as the standard `EventSource` API with auto-reconnect built in.

Cosign uses SSE for **live agent execution feedback**:
- When the user starts a goal (clicks "Review with Cosign" or "Resolve with Cosign"), the UI immediately opens `GET /stream/goals/{uuid}`.
- As the worker runs agent nodes, every state change (`task.started`, `task.tool_call`, `iteration.implementer`, `iteration.critic`, `gate.pending`, `goal.completed`) is published to a Redis Stream.
- `cosign-api`'s SSE multiplexer subscribes to the Redis Stream for that goal and fans out events to all connected browsers watching that goal.

**Why SSE, not WebSockets?**
- We only need server → client traffic for live updates. Client → server actions (cosign, revise, cancel) go through normal `POST` requests. SSE is a perfect fit for one-way streaming; WebSockets would be overkill.
- SSE goes over plain HTTPS — no special upgrade handshake — so it works through every CDN, load balancer, and corporate proxy without configuration.
- Built-in reconnect via `Last-Event-ID` header; the browser replays missed events automatically after a dropped connection.

**Webhooks are a separate thing entirely.** Webhooks are `POST` requests *from GitHub to us* when something happens on a connected repo (PR opened, issue assigned, etc.). Cosign uses them only as a **passive inbox feed** ("hey, there's a new PR on your repo you might want to review") — they **never** auto-trigger an agent run. Agents only run when the user clicks in the UI. See §7 for the GitHub integration detail.

### 1.3 What's a *driver* and what's a *DockerDriver*?

A **driver** is an interface (a "port" in hexagonal-architecture terms) that hides *how* a thing is done from *what* is done. Cosign's `SandboxDriver` interface defines the operations the worker needs to run an agent in an isolated environment (start a container, exec a command, read/write files, push a commit, stop). The interface is platform-agnostic.

**DockerDriver** is the v1 implementation of `SandboxDriver` that uses the local Docker daemon to create per-task containers — one container per agent run, isolated network, resource limits, ephemeral workspace, container destroyed when the run ends. This is what runs every agent's actual code execution on the Docker Compose deployment.

A **KubernetesDriver** (post-hackathon) will implement the same interface against the k8s API — creating Pods instead of containers. The rest of the worker code does not change; only the env var `SANDBOX_DRIVER=docker|k8s` selects which implementation is loaded. Full implementation detail in §6.

---

## 2. Internal Module Boundaries

### 2.1 cosign-api (Go) — internal packages

```
cosign-api/
├── cmd/
│   └── cosign-api/main.go        # single binary entrypoint
├── internal/
│   ├── gateway/                  # HTTP + JWT + SSE + GitHub webhook receiver
│   │   ├── server.go             # chi router setup
│   │   ├── middleware/           # auth, request_id, rate_limit, cors, recovery
│   │   ├── handlers/             # /goals, /agents, /reputation, /webhooks/github, /auth/*
│   │   ├── sse/                  # SSE multiplexer subscribing to Redis Streams
│   │   └── webhook/              # HMAC-SHA256 verify + event dispatch
│   ├── identity/                 # user + agent registry + capability checks
│   │   ├── users.go              # CRUD + OAuth-linked GitHub identities
│   │   ├── agents.go             # agent registry + capability JSON
│   │   ├── caps.go               # VerifyCapability(agent_id, tool_name) → bool
│   │   └── github_install.go     # GitHub App installation records
│   ├── reputation/               # composite score + leaderboard + badges
│   │   ├── score.go              # batched scoring job (tokio-equivalent: ticker)
│   │   ├── leaderboard.go        # Redis ZSET reads/writes
│   │   └── badges.go             # "Verified Run" badge engine
│   ├── orchestration/            # gRPC client to cosign-worker
│   │   └── client.go             # SubmitGoal, ResumeFromInterrupt, StreamEvents
│   ├── store/                    # sqlc-generated query layer (one package)
│   │   ├── queries/              # *.sql files → generated *_sql.go
│   │   └── db/                   # connection pool, migrations driver
│   ├── cache/                    # Redis helpers (typed wrappers)
│   │   ├── llm_exact.go
│   │   ├── tool_output.go
│   │   ├── plan.go
│   │   └── github_etag.go
│   └── config/                   # env-var loading, validation
└── pkg/                          # public types shared with cosign-web via TS codegen
    └── apitypes/                 # request/response structs
```

**Boundary rule:** packages under `internal/` may only import each other through *interfaces* defined in the consumer's package, never concrete types. This means `gateway` can call `identity.Verifier`, where `Verifier` is an interface defined inside `gateway`. Result: extracting `identity` to a separate service later is a 1-day swap (interface stays, implementation becomes a gRPC client).

### 2.2 cosign-worker (Python) — internal packages

```
cosign-worker/
├── pyproject.toml                # uv project
├── cosign_worker/
│   ├── __main__.py               # FastAPI app + gRPC server entrypoint
│   ├── orchestration/
│   │   ├── graph.py              # LangGraph StateGraph construction
│   │   ├── state.py              # AgentState TypedDict
│   │   ├── nodes/
│   │   │   ├── plan.py
│   │   │   ├── implementer.py
│   │   │   ├── reviewer.py
│   │   │   ├── critic.py
│   │   │   ├── critic_loop.py    # subgraph: implementer ↔ critic
│   │   │   └── finalize.py
│   │   ├── checkpoint.py         # AsyncPostgresSaver wiring
│   │   └── interrupts.py         # HITL gate helpers
│   ├── tools/
│   │   ├── base.py               # BaseTool with cache + capability check
│   │   ├── github.py             # github_ops, github_pr, fork-mode (all act as invoking user via OAuth)
│   │   ├── code.py               # code_exec (uses SandboxDriver)
│   │   ├── file_ops.py           # read/write/delete inside sandbox
│   │   ├── test_runner.py        # detect+run repo tests, parse results
│   │   ├── lint.py               # detect+run repo linter, parse violations
│   │   ├── repo_map.py           # tree-sitter-based repo structure + symbol map
│   │   ├── review.py             # structured review composition (used by reviewer agent)
│   │   ├── diff_analysis.py      # semantic diff classification + dangerous-pattern detection
│   │   └── search.py             # web_search via Brave/Serper
│   ├── sandbox/
│   │   ├── driver.py             # SandboxDriver Protocol
│   │   ├── docker_driver.py      # v1 implementation
│   │   └── handle.py             # SandboxHandle dataclass
│   ├── llm/
│   │   ├── router.py             # LiteLLM-backed multi-provider routing
│   │   ├── prompt_cache.py       # Anthropic cache_control / OpenAI auto-cache wrapper
│   │   └── health.py             # Redis-tracked provider health
│   ├── cache/                    # Redis helpers (mirror Go side)
│   │   ├── llm_exact.py
│   │   ├── tool_output.py
│   │   └── plan.py
│   ├── rpc/
│   │   ├── server.py             # gRPC server impl
│   │   └── pb/                   # generated protobuf code
│   ├── db/
│   │   └── pool.py               # asyncpg pool
│   └── config.py                 # env-var loading
└── tests/
```

**Boundary rule:** `nodes/` may import from `tools/`, `llm/`, `cache/`, `sandbox/`, `db/`, and `orchestration/state` — but never from `rpc/`. The gRPC server in `rpc/` is the only entrypoint that talks to outside services; nodes stay decoupled from transport.

### 2.3 cosign-web (Next.js)

```
cosign-web/
├── app/
│   ├── layout.tsx
│   ├── page.tsx                  # landing / dashboard
│   ├── goals/[id]/page.tsx       # goal detail + live SSE feed
│   ├── repos/page.tsx            # installed repos list
│   ├── inbox/page.tsx            # cosign queue (pending HITL gates)
│   ├── audit/page.tsx            # audit log viewer
│   ├── compare/page.tsx          # competitive comparison page (Day 7)
│   └── auth/                     # NextAuth or custom OAuth handlers
├── components/
│   ├── GoalDetail.tsx
│   ├── EventFeed.tsx             # SSE consumer
│   ├── CosignGate.tsx            # the gate modal (Flow A review + Flow B transcript)
│   ├── TranscriptViewer.tsx      # per-round collapsible transcript blocks
│   ├── DiffViewer.tsx
│   └── AuditLog.tsx
├── lib/
│   ├── api.ts                    # typed client; types generated from apitypes
│   ├── useSSE.ts                 # SSE hook with reconnect + Last-Event-ID
│   └── auth.ts
└── public/
```

---

## 3. Data Flow

**Both flows start the same way: the user clicks a button in `cosign-web`.** No webhooks trigger agent runs. Webhooks (if subscribed) only populate the user's inbox of "PRs/issues that exist on your connected repos" — the user still has to click [Review with Cosign] or [Resolve with Cosign] to start an agent.

### 3.1 Flow A — User-Initiated PR Review

```
User in cosign-web clicks [Review with Cosign] on a PR
(or pastes a PR URL into "Review any PR")
   │
   │  POST /goals { type:"pr_review", pr_url, user_id, options }
   ▼
cosign-api · handler /goals
   1. AuthZ: confirm user is signed in (JWT cookie)
   2. Resolve PR: extract owner/repo/number; look up repo in DB
      → if repo in user's installations: use App token for read
      → else: use user's OAuth token for read
   3. INSERT goals (type=pr_review, user_id, repo, pr_number, status=pending)
   4. INSERT audit_log (event=goal_created, actor=user)
   │
   │  gRPC: SubmitGoal(goal_id)
   ▼
cosign-worker · rpc/server
   1. Load goal from DB
   2. Fetch the invoking user's OAuth token (via identity service gRPC)
   3. Hydrate AgentState with: repo context, PR diff, user_oauth_token
   4. Start LangGraph thread (thread_id = goal_id:0)
   │
   ▼
LangGraph: plan_node → reviewer_node
   │
   ▼
reviewer_node
   1. DockerDriver.start → sandbox container per task
   2. Clone repo (uses user's OAuth token), checkout PR ref
   3. tools.repo_map → compact symbol map
   4. tools.file_ops (Redis cache hit on repeat) for relevant files
   5. tools.diff_analysis → classify hunks, detect dangerous patterns
   6. tools.lint (if applicable) → catch low-quality output early
   7. LLM call (Anthropic Sonnet) with prompt cache:
        - system + tool defs + repo_map (cached via cache_control)
        - PR diff + relevant files (NOT cached — dynamic)
   8. tools.review → composes a structured review draft
        { summary, risk_score, per_file_comments, ask_changes, praise }
   9. UPDATE tasks / INSERT messages
   │
   ▼
finalize_node
   1. INSERT interrupts (type=pr_review_gate, payload=review_draft)
   2. PUBLISH stream:goal:{goal_id} gate.pending
   3. graph.interrupt() — thread suspends
   │
   ▼
cosign-api · SSE multiplexer
   browser subscribed to /stream/goals/{uuid} → gate.pending → UI
   │
   ▼
cosign-web · ReviewEditor renders the draft INLINE (editable)
   User tweaks wording, then clicks [Cosign]
   POST /goals/{uuid}/resume { decision:"approve", edited_review:{...} }
   │
   ▼
cosign-api · handler
   1. UPDATE interrupts SET resolved_at, decision='approve', actor_user_id, payload
   2. INSERT audit_log (event=cosign_review, payload_hash=SHA256(edited_review))
   3. POST review on PR using the USER'S OAuth token (not bot)
        → GitHub PR shows the review authored by the user
   4. gRPC: ResumeFromInterrupt(goal_id, {decision, edited_review})
   │
   ▼
cosign-worker · finalize → END
   UPDATE goals SET status='done', completed_at=NOW
   INSERT audit_log (event=goal_completed)
   PUBLISH goal.completed
```

### 3.2 Flow B — User-Initiated Issue → PR

```
User in cosign-web clicks [Resolve with Cosign] on an issue
(or pastes an issue URL + optional steering note)
   │
   │  POST /goals { type:"issue_implement", issue_url, user_id, steer? }
   ▼
cosign-api · handler /goals
   1. AuthZ check
   2. Resolve issue → owner/repo/number; look up repo
      → if in user's installations: fork_mode=false
      → else: fork_mode=true (will require user OAuth token)
   3. INSERT goals (type=issue_implement, user_id, fork_mode, ...)
   4. INSERT audit_log (event=goal_created)
   │
   │  gRPC: SubmitGoal
   ▼
cosign-worker
   plan_node → critic_loop_subgraph
   │
   ▼
critic_loop_subgraph
   ┌────────────────────────────────────────────────┐
   │ iteration = 0                                  │
   │ LOOP:                                          │
   │   1. implementer_node                          │
   │        - if fork_mode: ensure user's fork      │
   │          exists; clone fork                    │
   │        - reads state.diff (empty round 0)      │
   │        - reads state.critic_feedback (empty 0) │
   │        - reads user steering note (if present) │
   │        - tools.test_runner + tools.lint        │
   │        - emits new diff + self_satisfaction    │
   │        - INSERT critic_iterations              │
   │        - PUBLISH iteration.implementer (SSE)   │
   │   2. IF self_satisfaction >= threshold         │
   │         OR iteration >= max_iters: BREAK       │
   │   3. critic_node                               │
   │        - tools.diff_analysis + tools.test_runner│
   │        - emits structured feedback             │
   │        - UPDATE critic_iterations              │
   │        - PUBLISH iteration.critic (SSE)        │
   │   4. iteration += 1                            │
   └────────────────────────────────────────────────┘
   │
   ▼
finalize_node
   INSERT interrupts (type=critic_loop_gate, payload={transcript, final_diff})
   PUBLISH gate.pending
   graph.interrupt()
   │
   ▼
Browser ← SSE gate.pending → CosignGate + TranscriptViewer
   User cosigns
   POST /goals/{uuid}/resume { decision:"approve" }
   │
   ▼
cosign-worker resumes
   1. Push branch using USER'S OAuth token
        - fork_mode=false: push to origin repo
        - fork_mode=true: push to user's fork
   2. Open PR using USER'S OAuth token
        - PR is authored by the USER (no bot identity)
        - fork_mode=true: head = {user_login}:{branch} → upstream
   │
   ▼
finalize → END
```

---

## 4. Database Schema

PostgreSQL 16 + pgvector (extension installed but not used in v1). All tables use `BIGSERIAL` for internal IDs and `UUID` for externally-exposed IDs.

### 4.1 Users + GitHub App Installations

```sql
CREATE TABLE users (
    id              BIGSERIAL PRIMARY KEY,
    uuid            UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    github_id       BIGINT UNIQUE NOT NULL,
    github_login    TEXT NOT NULL,
    github_oauth_token_encrypted BYTEA,           -- AES-GCM at rest
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at   TIMESTAMPTZ
);

CREATE TABLE installations (
    id                  BIGSERIAL PRIMARY KEY,
    github_installation_id BIGINT UNIQUE NOT NULL,
    account_login       TEXT NOT NULL,             -- user or org login
    account_type        TEXT NOT NULL,             -- 'User' | 'Organization'
    installed_by_user_id BIGINT REFERENCES users(id),
    suspended_at        TIMESTAMPTZ,
    installed_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE repositories (
    id                  BIGSERIAL PRIMARY KEY,
    github_repo_id      BIGINT UNIQUE NOT NULL,
    full_name           TEXT NOT NULL,             -- "octocat/hello-world"
    installation_id     BIGINT REFERENCES installations(id),   -- NULL = fork-mode only
    default_branch      TEXT NOT NULL DEFAULT 'main',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_repos_install ON repositories(installation_id);
```

### 4.2 Agents

```sql
CREATE TABLE agents (
    id              BIGSERIAL PRIMARY KEY,
    uuid            UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    role            TEXT NOT NULL,           -- 'implementer' | 'reviewer' | 'critic'
    display_name    TEXT NOT NULL,
    capabilities    JSONB NOT NULL,          -- {tools: [...], repos: [...], trust_level: int}
    capability_hash TEXT NOT NULL,           -- SHA-256 of capabilities JSON
    active          BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 4.3 Goals + Tasks

```sql
CREATE TABLE goals (
    id              BIGSERIAL PRIMARY KEY,
    uuid            UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    user_id         BIGINT NOT NULL REFERENCES users(id),
    repository_id   BIGINT REFERENCES repositories(id),
    type            TEXT NOT NULL,            -- 'pr_review' | 'issue_implement' | 'manual'
    title           TEXT NOT NULL,
    description     TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
                                              -- pending | planning | executing | awaiting_human | done | failed | cancelled
    github_pr_number    INTEGER,
    github_issue_number INTEGER,
    fork_mode       BOOLEAN NOT NULL DEFAULT FALSE,
    output_json     JSONB,
    error           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX idx_goals_user_status ON goals(user_id, status);
CREATE INDEX idx_goals_repo        ON goals(repository_id);
CREATE INDEX idx_goals_created     ON goals(created_at DESC);

CREATE TABLE tasks (
    id              BIGSERIAL PRIMARY KEY,
    uuid            UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    goal_id         BIGINT NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    agent_id        BIGINT REFERENCES agents(id),
    agent_role      TEXT NOT NULL,
    tool_name       TEXT,
    args_json       JSONB,
    args_hash       TEXT,                     -- SHA-256(args_json) for idempotency
    status          TEXT NOT NULL DEFAULT 'pending',
    result_json     JSONB,
    result_hash     TEXT,                     -- SHA-256(result_json)
    error           TEXT,
    attempt_count   INTEGER DEFAULT 0,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ
);

CREATE TABLE task_dependencies (
    task_id         BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    depends_on_id   BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    PRIMARY KEY (task_id, depends_on_id)
);
```

### 4.4 Critic Iterations (Flow B transcript)

```sql
CREATE TABLE critic_iterations (
    id                  BIGSERIAL PRIMARY KEY,
    goal_id             BIGINT NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    round_number        INTEGER NOT NULL,        -- 0, 1, 2, ...
    implementer_prompt  JSONB NOT NULL,
    implementer_diff    TEXT,
    self_satisfaction   NUMERIC(3,2),            -- 0.00 to 1.00
    critic_prompt       JSONB,                   -- NULL on the final round when loop exited by score
    critic_feedback     JSONB,                   -- { blocking_issues, suggestions, score }
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    UNIQUE (goal_id, round_number)
);

CREATE INDEX idx_critic_iter_goal ON critic_iterations(goal_id, round_number);
```

### 4.5 LLM Messages (per-task history)

```sql
CREATE TABLE messages (
    id          BIGSERIAL PRIMARY KEY,
    task_id     BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    role        TEXT NOT NULL,           -- 'system' | 'user' | 'assistant' | 'tool'
    content     TEXT NOT NULL,
    tool_name   TEXT,
    tool_args   JSONB,
    tokens_in   INTEGER,
    tokens_out  INTEGER,
    cached_tokens INTEGER,               -- from provider (Anthropic cache_read / OpenAI cached)
    cost_usd    NUMERIC(10,6),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_messages_task ON messages(task_id);
```

### 4.6 Interrupts (HITL gates)

```sql
CREATE TABLE interrupts (
    id              BIGSERIAL PRIMARY KEY,
    uuid            UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    goal_id         BIGINT NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    type            TEXT NOT NULL,        -- 'pr_review_gate' | 'critic_loop_gate' | 'dangerous_code' | 'steer'
    payload_json    JSONB NOT NULL,       -- the artifact the human is reviewing
    decision        TEXT,                 -- 'approve' | 'revise' | 'reject' | NULL while pending
    feedback        TEXT,                 -- free text for 'revise' or 'steer'
    actor_user_id   BIGINT REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ
);

CREATE INDEX idx_interrupts_pending ON interrupts(goal_id) WHERE resolved_at IS NULL;
```

### 4.7 Audit Log (replaces on-chain audit from reference)

```sql
CREATE TABLE audit_log (
    id              BIGSERIAL PRIMARY KEY,
    actor_type      TEXT NOT NULL,        -- 'user' | 'agent' | 'system'
    actor_id        BIGINT,               -- user_id or agent_id
    event_type      TEXT NOT NULL,        -- 'goal_created' | 'tool_call' | 'cosign' | 'goal_completed' | ...
    goal_id         BIGINT REFERENCES goals(id),
    payload_json    JSONB,
    payload_hash    TEXT,                 -- SHA-256 of payload (for later verifiability)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_goal       ON audit_log(goal_id, created_at DESC);
CREATE INDEX idx_audit_actor      ON audit_log(actor_type, actor_id, created_at DESC);
CREATE INDEX idx_audit_event_type ON audit_log(event_type, created_at DESC);
```

### 4.8 Reputation (Optional v1)

Kept simple — no on-chain submission, no partitioned snapshots. Just enough to drive a leaderboard.

```sql
CREATE TABLE reputation (
    agent_id        BIGINT PRIMARY KEY REFERENCES agents(id),
    score           INTEGER NOT NULL DEFAULT 0,    -- 0–10000
    tasks_attempted INTEGER NOT NULL DEFAULT 0,
    tasks_completed INTEGER NOT NULL DEFAULT 0,
    cosigns_approved INTEGER NOT NULL DEFAULT 0,
    cosigns_rejected INTEGER NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE badges (
    id          BIGSERIAL PRIMARY KEY,
    agent_id    BIGINT NOT NULL REFERENCES agents(id),
    badge_type  TEXT NOT NULL,            -- 'verified_run' | 'streak_10' | etc.
    issued_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 4.9 LangGraph Checkpoints

LangGraph's `AsyncPostgresSaver` manages its own tables (`checkpoints`, `checkpoint_writes`, `checkpoint_blobs`). Created via `await checkpointer.setup()` on worker startup. Not enumerated here.

---

## 5. Cost Optimization — Caching + Per-Role LLM Routing

Cost optimization is a first-class architectural concern, not an afterthought. Two systems work together: a **5-layer cache stack** (this section) and a **per-role / per-tool LLM router** (see §5.7). Combined target: **<$0.10 per shipped Flow B PR** (vs ~$0.45 if everything ran on Claude Sonnet end-to-end). See PRD §6.8 for the product-level pitch.

### 5.0 Cache stack overview

Five layers operate in priority order. Cheapest checks run first. Each layer is independent — failure of one does not break the others.

```
LLM call site
   │
   ├─► [Redis] LLM exact-hash cache hit? ─YES─► return cached response
   │   key: llm:exact:{sha256(model + messages + temp_bucket)}
   │   TTL: 24h
   │
   ├─► [Provider] Anthropic / OpenAI prompt cache hit?
   │   wired via cache_control marker (Anthropic) or just stable prefix (OpenAI)
   │   savings: 90% on cached input tokens (Anthropic), free on OpenAI
   │
   └─► full LLM call → write to L1 exact-hash cache on return

Tool call site
   │
   ├─► capability check (identity.VerifyCapability)
   │
   ├─► [Redis] tool output cache hit? ─YES─► return cached result
   │   key: tool:{name}:{sha256(args)}
   │   TTL: per-tool (see §5.3)
   │
   └─► [Redis] (for github_ops only) ETag cache: send If-None-Match
       304 → return cached body
       200 → store new etag + body, return body

Plan site (LangGraph plan_node)
   │
   ├─► [Redis] plan cache hit? ─YES─► reuse DAG, interpolate context
   │   key: plan:{sha256(goal_description)}
   │   TTL: 12h
   │
   └─► full LLM planning call
```

### 5.1 Provider Prompt Cache (L2)

**Anthropic** — explicit `cache_control` marker on the system block:

```python
response = client.messages.create(
    model="claude-sonnet-4-6",
    system=[
        {
            "type": "text",
            "text": SYSTEM_PROMPT + TOOL_DEFINITIONS + REPO_CONTEXT,
            "cache_control": {"type": "ephemeral"}
        }
    ],
    messages=[{"role": "user", "content": dynamic_user_prompt}],
    max_tokens=2048,
)
# response.usage.cache_read_input_tokens shows how many tokens were served from cache
```

Static-content-first / dynamic-content-last rule strictly observed. Any change to anything before the cache breakpoint invalidates the entire cache.

**OpenAI** — automatic, no marker. Prefix must be ≥1024 tokens. Cache hits in 128-token increments.

**Break-even math (from the caching guide):** 1.25× write premium / 0.9× per-hit savings ≈ 1.4 hits to break even on 5-min TTL; or 2× write premium / 0.9× per-hit savings ≈ 2.2 hits for 1-hour TTL. Our reviewer + implementer + critic re-use the same system prefix dozens of times per goal, so we're well past break-even on every goal.

### 5.2 Redis LLM Exact-Hash Cache (L1)

```
key:  llm:exact:{sha256(model | messages_json | temp_bucket)}
type: HASH { response, prompt_tokens, completion_tokens, cached_at }
TTL:  24h
```

`temp_bucket` is one of `"low"` (≤0.3), `"medium"` (0.3–0.7), `"high"` (>0.7) — keeps minor temperature drift from busting the cache.

### 5.3 Tool Output Cache

```
key:  tool:{name}:{sha256(args_json)}
type: HASH { result_json, cached_at }
TTL:  per-tool:
        github_ops (reads): 5 minutes  (revalidated via ETag — see §5.4)
        file_ops (reads):   10 minutes (workspace files don't change mid-task)
        web_search:         1 hour
        github_ops (writes): NEVER CACHED
        code_exec:          NEVER CACHED
```

Write-side and side-effectful tools are never cached. The cache wrapper is opt-in per tool (set in `BaseTool.cacheable: bool`).

### 5.4 GitHub ETag Cache

```
key:  github:etag:{sha256(url + auth_id)}
type: HASH { etag, body_json, fetched_at }
TTL:  5 minutes
```

On every github_ops read:
1. Look up cached `{etag, body}`.
2. Send `If-None-Match: {etag}` header.
3. If 304 → return cached `body` (counts as a hit; refresh TTL).
4. If 200 → update cache with new `{etag, body}`; return body.

GitHub does not count 304s against rate limits, so this is essentially free.

### 5.5 Plan Cache

```
key:  plan:{sha256(goal_description.normalized)}
type: HASH { dag_json, original_goal_id, created_at }
TTL:  12h
```

Normalization: lowercase, collapse whitespace, strip URLs and ticket numbers. Hits when a user retries a very similar goal.

### 5.6 Invalidation

TTL-only. No active invalidation in v1. Users can force a miss by submitting `X-Cache-Bypass: true` on the goal-create request (skips L1 LLM cache + plan cache; provider prompt cache is still consulted because the provider doesn't honor a bypass header).

### 5.7 Per-Role LLM Routing

Different nodes have different intelligence requirements. The router maps each role / tool to its own `(provider, model, api_key_env)` triple so cheap workloads use cheap models and premium spend is reserved for value-critical steps.

**Config (loaded at worker startup from `config/llm-routing.yaml`):**

```yaml
# config/llm-routing.yaml
defaults:
  provider: anthropic
  model: claude-sonnet-4-6
  api_key_env: ANTHROPIC_API_KEY
  temperature: 0.2
  fallback:
    - { provider: openai,    model: gpt-4o,                api_key_env: OPENAI_API_KEY }

roles:
  plan_node:
    provider: anthropic
    model: claude-haiku-4-5-20251001
    api_key_env: ANTHROPIC_CHEAP_API_KEY          # operator can use a separate billing key
    temperature: 0.0
    fallback:
      - { provider: groq, model: llama-3.3-70b,   api_key_env: GROQ_API_KEY }
      - { provider: openai, model: gpt-4o-mini,    api_key_env: OPENAI_API_KEY }

  critic:
    provider: groq
    model: llama-3.3-70b
    api_key_env: GROQ_API_KEY
    temperature: 0.1
    fallback:
      - { provider: anthropic, model: claude-haiku-4-5-20251001, api_key_env: ANTHROPIC_CHEAP_API_KEY }

  implementer:
    # uses defaults (Sonnet) — explicit override would go here

  reviewer:
    # uses defaults (Sonnet)

tools:
  diff_analysis:
    provider: anthropic
    model: claude-haiku-4-5-20251001
    api_key_env: ANTHROPIC_CHEAP_API_KEY

  repo_map:
    provider: none        # purely local tree-sitter — no LLM call
  lint:
    provider: none
  test_runner:
    provider: none
```

**Code path (single entrypoint):**

```python
# cosign_worker/llm/router.py
from litellm import acompletion

class LLMRouter:
    def __init__(self, routing_config: dict):
        self.cfg = routing_config

    def _resolve(self, role: str | None, tool: str | None) -> dict:
        if tool and tool in self.cfg.get("tools", {}):
            return self.cfg["tools"][tool]
        if role and role in self.cfg.get("roles", {}):
            return self.cfg["roles"][role]
        return self.cfg["defaults"]

    async def acall(
        self, *, role: str | None = None, tool: str | None = None,
        messages: list, **kw,
    ) -> "Completion":
        spec = self._resolve(role, tool)
        if spec.get("provider") == "none":
            raise ValueError(f"role={role} tool={tool} configured as 'none' — no LLM call")

        # Try primary, then fallbacks
        chain = [spec] + spec.get("fallback", [])
        last_err = None
        for s in chain:
            try:
                return await acompletion(
                    model=f"{s['provider']}/{s['model']}",
                    api_key=os.environ[s["api_key_env"]],
                    messages=messages,
                    temperature=s.get("temperature", 0.2),
                    **kw,
                )
            except Exception as e:
                last_err = e
                await self._record_provider_health(s["provider"], failed=True)
                continue
        raise last_err
```

**Every LangGraph node calls through the router with its role:**

```python
async def plan_node(state):
    resp = await router.acall(role="plan_node", messages=build_plan_messages(state))
    ...

async def critic_node(state):
    resp = await router.acall(role="critic", messages=build_critic_messages(state))
    ...
```

**Why this design:**
- **Operator-controlled, not user-controlled.** Routing config is a deploy-time concern; users don't see it.
- **Per-role API keys.** An operator can use a high-cost-but-rate-limited Anthropic Sonnet key for implementer and a separate cheaper Anthropic Haiku key (or a Groq key) for plan/critic. Billing separation falls out for free.
- **Health-tracked fallback chains** per role. If Groq is down, critic falls through to Haiku.
- **`provider: none` is valid** for tools that don't actually need an LLM (lint, test_runner, repo_map run deterministic local code).
- **No code changes when routing changes.** A new model from any provider is a YAML edit + restart.

### 5.8 Per-Goal Cost Tracking

The `messages` table (see §4.5) already records `tokens_in`, `tokens_out`, `cached_tokens`, `cost_usd` per LLM call. Per-goal cost aggregation is a single GROUP-BY:

```sql
-- cost breakdown per role for a single goal
SELECT
    t.agent_role,
    COUNT(*) FILTER (WHERE m.role = 'assistant')             AS call_count,
    SUM(m.tokens_in)                                          AS tokens_in,
    SUM(m.tokens_out)                                         AS tokens_out,
    SUM(m.cached_tokens)                                      AS cached_tokens,
    ROUND(SUM(m.cost_usd)::numeric, 4)                        AS cost_usd
FROM messages m
JOIN tasks t ON m.task_id = t.id
WHERE t.goal_id = $1
GROUP BY t.agent_role
ORDER BY cost_usd DESC;
```

Surfaced in:
- `GET /goals/{uuid}` response: `cost_breakdown: [...]` field.
- Goal-detail UI: cost-by-role bar at the top of the page.
- `/metrics` Prometheus exposition: `cosign_worker_goal_cost_usd_sum{role}` counter.

---

## 6. Sandbox Architecture

### 6.1 The SandboxDriver Protocol

The sandbox is the most operationally divergent piece between Docker (v1) and Kubernetes (post-hackathon). Keeping it behind an interface keeps the rest of the codebase identical.

```python
# cosign_worker/sandbox/driver.py
from typing import Protocol, runtime_checkable
from dataclasses import dataclass

@dataclass
class SandboxHandle:
    id: str                  # opaque to callers
    container_id: str        # Docker container ID or k8s pod name
    workspace_path: str      # path inside the container/pod
    repo_url: str
    branch: str
    created_at: float

@dataclass
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_s: float

@dataclass
class CommitInfo:
    sha: str
    branch: str
    pushed: bool

@runtime_checkable
class SandboxDriver(Protocol):
    async def start(
        self, task_id: str, image: str, repo_url: str,
        branch: str, github_token: str, *, timeout_s: int = 30,
    ) -> SandboxHandle: ...

    async def exec(
        self, handle: SandboxHandle, cmd: list[str], *,
        cwd: str | None = None, timeout_s: int = 30,
        env: dict[str, str] | None = None,
    ) -> ExecResult: ...

    async def read_file(self, handle: SandboxHandle, path: str) -> bytes: ...
    async def write_file(self, handle: SandboxHandle, path: str, content: bytes) -> None: ...
    async def list_files(self, handle: SandboxHandle, path: str, *, recursive: bool = False) -> list[str]: ...

    async def commit_and_push(
        self, handle: SandboxHandle, branch: str, message: str,
        *, force: bool = False,
    ) -> CommitInfo: ...

    async def stop(self, handle: SandboxHandle) -> None: ...
```

### 6.2 DockerDriver (v1)

Implementation specifics:

- **Image:** `cosign/sandbox:latest` — a slim image with `git`, `node`, `python`, `bash`, `curl`. Built from `infra/sandbox.Dockerfile`. ~250 MB.
- **Container per task** — never reused across tasks (clean state guarantee).
- **Resource limits:** `--memory=2g --cpus=2 --pids-limit=512`.
- **Network:** `--network=cosign_sandbox_net`, a Docker network with egress allowed only to `api.github.com`, `*.githubusercontent.com`, npm/pypi registries (managed via iptables in a sidecar). Blocks SSRF to internal services.
- **Filesystem:** `--read-only` root + `--tmpfs /tmp:size=512m` + a dedicated bind-mount workspace per container.
- **Auth:** GitHub token passed in as `GIT_ASKPASS` helper, never written to disk; stripped from env before agent commands run.
- **Lifecycle:** containers older than 30 min are reaped by a periodic janitor goroutine (defense against leaked handles).

### 6.3 KubernetesDriver (post-hackathon)

Stub-only in v1. Will create a Pod via the k8s API with similar limits, mount an emptyDir for the workspace, and use the same env-var contract. Swapping drivers requires changing only the `SANDBOX_DRIVER` env var (`docker` | `k8s`).

---

## 7. GitHub Integration

Cosign is a web app, not a bot. GitHub is integrated for two reasons only:

1. **Authentication and acting-as-the-user** — OAuth + (optional) GitHub App install give Cosign permission to read PRs/issues and post reviews/comments/PRs **as the invoking user**, never as a `cosign[bot]` identity.
2. **Inbox feed (optional)** — webhooks, if subscribed, populate a personal inbox of "things on your repos you might want to work on" in the Cosign UI. Webhooks **never** auto-trigger agent runs.

### 7.1 OAuth Login (required for all users)

Every Cosign user signs in with GitHub OAuth. The scopes requested:

- `read:user` — basic profile (for the UI)
- `public_repo` — read+write to public repos on the user's behalf (covers Flow A on any public PR, Flow B fork-mode for any public issue→PR)

The OAuth token is stored AES-GCM-encrypted on the `users` row. The worker fetches it on demand via the identity service's `GetUserOAuthToken` gRPC, decrypts in memory, uses it for the per-goal GitHub calls, and discards. Never written to logs.

If a user wants Cosign to act on a *private* repo, they re-auth with the `repo` scope (broader). This is an optional upgrade; v1 defaults to `public_repo` to minimize trust ask.

### 7.2 GitHub App Install (optional — for write-access on connected repos)

A user can install the Cosign GitHub App on their own repos or orgs. This gives Cosign privileged access (App token, scoped per-installation) that's used for **read-side optimizations only** (higher rate limits, ability to subscribe to webhooks). All write actions still use the user's OAuth token so the PR/review/comment is attributed to the user.

**App scopes (minimum):**
- `contents:read` — efficient clone/diff fetch with higher rate limits
- `pull_requests:read` — fetch PRs and review threads
- `issues:read` — fetch issues
- `metadata:read` — basic repo info

Note: no `*:write` scopes on the App. Writes always go through user OAuth.

**Webhook events subscribed (passive inbox feed only — do NOT trigger agents):**
- `pull_request.opened` → INSERT into `inbox_items` so the user sees "new PR on your repo"
- `pull_request.synchronize` → mark inbox item as updated
- `issues.opened` / `issues.assigned` → inbox item
- `installation.created` / `installation.deleted` → maintain `installations` table

**No slash commands in v1.** The UI is the only entrypoint. `/cosign review` etc. are an explicit non-goal (see PRD §7 Out of Scope). Could be re-added post-hackathon if there's demand.

**HMAC verification:** every webhook payload is verified with `X-Hub-Signature-256` against the App's webhook secret. Mismatch → 401, no DB writes.

### 7.3 Fork-mode (for repos the user doesn't own)

Triggered automatically whenever a user-initiated goal targets a repo not in their `installations`. Flow:

```
1. User clicks [Review with Cosign] or [Resolve with Cosign]
   on a repo not in their installations
2. cosign-api: fork_mode=true on the goal
3. cosign-worker uses USER'S OAuth token to:
     a. POST /repos/{upstream_owner}/{repo}/forks
        → creates or returns {user_login}/{repo} (idempotent)
     b. Clones the fork into the sandbox
        (after `git fetch upstream && git reset --hard upstream/{default}`
         to avoid stale state if the fork already existed)
     c. Runs the agent flow as normal
     d. (Flow B only) Pushes branch to the user's fork
     e. (Flow B only) POST /repos/{upstream_owner}/{repo}/pulls
          with head={user_login}:{branch}
          → opens the PR upstream, authored by the user
     f. (Flow A only) POST review on the upstream PR with the user's OAuth
4. cosign-api records the upstream PR/review URL on the goal + audit log
```

**Critical detail:** every side-effectful action (the review, the PR, the comment) is authored by the user because the user's OAuth token is what made the call. No `cosign[bot]` identity exists anywhere in the system.

**Abuse mitigation:** fork-mode goals are rate-limited per user (default 5/hour, configurable). A repo allowlist can be set for public demo deployments to prevent the platform being abused to spam upstream maintainers.

---

## 8. API Surface

Standard envelope:
```json
{ "data": { ... }, "meta": { "request_id": "...", "timestamp": "..." }, "error": null }
```

### 8.1 Goals

```
POST   /goals                     Submit a new goal
GET    /goals                     List goals (filter by status, repo, user)
GET    /goals/{uuid}              Goal detail + tasks + transcript + interrupts
POST   /goals/{uuid}/resume       Resume from interrupt (body: { decision, feedback? })
DELETE /goals/{uuid}              Cancel a running goal
GET    /goals/{uuid}/audit        Full audit trail for the goal (download as JSON)
GET    /goals/{uuid}/transcript   Export iteration transcript (Flow B only)
```

### 8.2 Webhooks + Auth

```
POST   /webhooks/github           GitHub App webhook receiver (HMAC verified)
GET    /auth/github/login         Initiate GitHub OAuth (for fork-mode + UI login)
GET    /auth/github/callback      OAuth callback
GET    /auth/github/install       Redirect to GitHub App installation
POST   /auth/logout
GET    /auth/me                   Current user
```

### 8.3 Streaming

```
GET    /stream/goals/{uuid}       SSE: task events + gate.pending + iteration events
GET    /stream/inbox              SSE: all gate.pending events the user has access to
```

SSE events the client should handle:
- `goal.status_changed`, `task.started`, `task.tool_call`, `task.completed`, `task.failed`
- `iteration.implementer` (Flow B, includes round number + self_satisfaction)
- `iteration.critic` (Flow B, includes round number + feedback)
- `gate.pending` (UI shows CosignGate modal)
- `gate.resolved` (UI dismisses modal)
- `goal.completed`, `goal.failed`, `goal.cancelled`

### 8.4 Agents + Reputation

```
GET    /agents                    List agents (registry)
GET    /agents/{uuid}             Agent detail + capabilities + recent runs
GET    /reputation/leaderboard    Top-N agents
GET    /reputation/agents/{uuid}  Score + components for one agent
```

### 8.5 Audit

```
GET    /audit                     Audit log query (filter by goal, actor, event_type, date range)
GET    /audit/export              Download as JSONL
```

### 8.6 Health + Metrics

```
GET    /health                    Per-service liveness/readiness
GET    /metrics                   Prometheus exposition
```

---

## 9. Security and Trust

### 9.1 Authentication

- **User auth:** GitHub OAuth → server-issued JWT (RS256, 24h TTL, refresh via OAuth) in HttpOnly + SameSite=Lax cookie.
- **Agent auth (worker→api):** mTLS between services on the internal Docker network. The worker also includes a `X-Worker-Token` HS256 JWT on each call as a defense-in-depth.
- **Webhook auth:** HMAC-SHA256 on every payload using the App's webhook secret. Constant-time compare.

### 9.2 Authorization

Every tool call is gated by `identity.VerifyCapability(agent_id, tool_name)`:

```python
# cosign_worker/tools/base.py
async def call_tool(agent_id, tool_name, args, ...):
    if not await identity_client.verify_capability(agent_id, tool_name):
        raise PermissionError(f"agent {agent_id} not permitted to call {tool_name}")
    ...
```

Capabilities are set at agent registration. Capability JSON is hashed (SHA-256) and the hash is stored on the agent row — any tampering invalidates the hash on next verification.

### 9.3 Sandbox Isolation

- No host filesystem mounts beyond the dedicated workspace bind.
- No Docker socket mount inside the sandbox.
- Egress firewall whitelist (see §6.2).
- Resource limits prevent fork-bombs and OOM-ing the host.
- Workspace is wiped on `stop()`.

### 9.4 Secrets

- All secrets via env vars in v1, sourced from a `.env` file in dev and Docker secrets in compose-prod.
- Encrypted at rest: user OAuth tokens (AES-GCM with a key from env).
- Never logged: tool args containing tokens are filtered through a redactor before logging.

### 9.5 Dangerous-Action Gate

The implementer's own output is checked before any push for:
- Deletion of >50% of a file
- Modification of CI config files (`.github/workflows/*`, `*.yml` in repo root)
- Patterns matching known secret formats (AWS, GitHub PAT, Stripe, Anthropic, OpenAI keys)
- Modifying `package.json` scripts in suspicious ways (e.g., adding network calls in install scripts)

A match triggers a `dangerous_code` interrupt that requires explicit human Allow before the push happens.

---

## 10. Deployment

### 10.1 v1 — Docker Compose (hackathon)

Single `infra/docker-compose.yml` on a single VM (Hetzner CX22 or DigitalOcean basic droplet):

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    volumes: [postgres_data:/var/lib/postgresql/data]
  redis:
    image: redis:7-alpine
    volumes: [redis_data:/data]
  cosign-api:
    build: ./services/cosign-api
    depends_on: [postgres, redis]
    ports: ["8080:8080"]
  cosign-worker:
    build: ./services/cosign-worker
    depends_on: [postgres, redis, cosign-api]
    volumes: [/var/run/docker.sock:/var/run/docker.sock]   # DockerDriver needs this
  cosign-web:
    build: ./services/cosign-web
    depends_on: [cosign-api]
    ports: ["3000:3000"]
  caddy:
    image: caddy:2
    ports: ["80:80", "443:443"]
    volumes: [./caddy/Caddyfile:/etc/caddy/Caddyfile, caddy_data:/data]
```

Caddy terminates TLS (auto-Let's Encrypt) and reverse-proxies to the api + web services.

### 10.2 k8s-Ready Rules Followed From Day 1

These cost nothing in v1 and make the Docker→k8s port a ~1 day exercise:

1. **Stateless services** — Postgres + Redis hold all state. Sandbox workspaces are ephemeral.
2. **Env-var config only** — no config files baked into images.
3. **`/health` on every service** — used by Compose `depends_on: condition: service_healthy` AND by k8s liveness/readiness probes.
4. **Single binary / single entrypoint per service** — Compose `CMD` and k8s `command` are identical.
5. **SandboxDriver behind an interface** — `DockerDriver` for Compose, `KubernetesDriver` for k8s. Swap by env var.

### 10.3 Post-Hackathon k8s Port

Estimated 1 day of work:
1. Write `Deployment`/`Service`/`ConfigMap`/`Secret` manifests (one per service).
2. Write a `KubernetesDriver` implementing `SandboxDriver` against the k8s API (creates Pods in a `cosign-sandboxes` namespace).
3. Add `HorizontalPodAutoscaler` for api + web. Worker stays at 1 replica until we implement work-distribution.
4. Add `NetworkPolicy` matching the sandbox firewall rules from §6.2.

---

## 11. Observability

### 11.1 Logging

- **Format:** structured JSON, one line per log event.
- **Fields:** `ts`, `level`, `service`, `request_id`, `user_id?`, `goal_id?`, `task_id?`, `msg`, plus event-specific fields.
- **Library:** `slog` (Go), `structlog` (Python).
- **Shipping:** stdout in Compose; loki + Promtail post-hackathon.

### 11.2 Metrics

Each service exposes `/metrics` (Prometheus exposition):

**cosign-api:**
- `cosign_api_http_request_duration_seconds{method,route,status}` histogram
- `cosign_api_sse_connections_active` gauge
- `cosign_api_grpc_calls_total{rpc,status}` counter

**cosign-worker:**
- `cosign_worker_goals_active` gauge
- `cosign_worker_llm_calls_total{provider,model,cache_hit}` counter
- `cosign_worker_llm_tokens_total{provider,model,direction,cached}` counter
- `cosign_worker_cache_hits_total{cache}` counter (cache ∈ {llm_exact, tool_output, plan, github_etag})
- `cosign_worker_critic_iterations` histogram (rounds per Flow B goal)
- `cosign_worker_sandbox_active` gauge

**Both:**
- `cosign_build_info{version,commit}` constant gauge

### 11.3 Tracing (optional v1)

Jaeger via OTLP if there's time on Day 7. Otherwise rely on `request_id` correlation across logs. OpenTelemetry SDK integration is a post-hackathon task.

---

*Implementation order, day-by-day exit criteria, and risk register live in [ROADMAP.md](./ROADMAP.md). Product scope and rationale live in [PRD.md](./PRD.md).*
