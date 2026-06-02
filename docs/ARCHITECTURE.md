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
│   │              │  │  ├─ tools.github                     │     │
│   │ StateGraph:  │  │  ├─ tools.code   (uses SandboxDriver)│     │
│   │  implementer │  │  ├─ tools.file_ops                   │     │
│   │  reviewer    │  │  └─ tools.search                     │     │
│   │  critic loop │  │                                      │     │
│   │  HITL gates  │  │ SandboxDriver protocol               │     │
│   │  checkpoint  │  │  └─ DockerDriver (v1)                │     │
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
| Browser ↔ cosign-api | HTTPS + SSE (+ WSS later) | SSE for live event feed during agent runs; standard REST for everything else |
| cosign-api ↔ cosign-worker | gRPC (HTTP/2) | Typed contracts, bidirectional streaming for orchestration events back to api, fast (~1ms p50 over localhost) |
| cosign-api ↔ Postgres | TCP (sqlc-generated queries) | Compile-time-safe SQL in Go via sqlc |
| cosign-worker ↔ Postgres | TCP (asyncpg) | LangGraph `AsyncPostgresSaver` uses asyncpg; tool servers share the pool |
| Both services ↔ Redis | TCP (go-redis / redis-py) | Caches, Streams, SortedSet |
| cosign-worker ↔ sandbox containers | Docker SDK (HTTP+UDS) | DockerDriver invokes the local Docker socket |
| cosign-worker ↔ LLM providers | HTTPS | Anthropic / Groq / OpenAI via LiteLLM router |
| cosign-worker ↔ GitHub | HTTPS | go-github equivalent in Python: `PyGithub` or `githubkit` |

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
│   │   ├── github.py             # github_ops, github_pr, fork-mode helpers
│   │   ├── code.py               # code_exec (uses SandboxDriver)
│   │   ├── file_ops.py           # read/write/delete inside sandbox
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

### 3.1 Flow A — PR Review with Human Gate (own repo)

```
GitHub PR opened
   │
   │  POST /webhooks/github (HMAC-SHA256 signed)
   ▼
cosign-api · gateway/webhook
   1. Verify HMAC
   2. Lookup installation by installation_id
   3. INSERT goals (type=pr_review, repo_id, pr_number, status=pending)
   4. INSERT audit_log (event=goal_created, ...)
   │
   │  gRPC: SubmitGoal(goal_id)
   ▼
cosign-worker · rpc/server
   1. Load goal from DB
   2. Hydrate AgentState with repo context + PR diff
   3. Start LangGraph thread (thread_id = goal_id:0)
   │
   ▼
LangGraph nodes (cosign-worker)
   plan_node → reviewer_node (single task)
   │
   ▼
reviewer_node
   1. Acquire sandbox handle (DockerDriver.start)
   2. Clone repo, checkout PR ref
   3. Read diff + relevant files via file_ops (Redis cache hit on repeat)
   4. Call LLM (Anthropic Sonnet) with:
        - system prompt: cached via cache_control
        - tool definitions: cached
        - repo + diff: NOT cached (dynamic)
   5. Parse structured review artifact
   6. UPDATE tasks SET status='done', result_json=...
   7. INSERT messages for LLM audit
   │
   ▼
finalize_node
   1. INSERT interrupts (type=pr_review_gate, payload=review_artifact)
   2. PUBLISH stream:goal:{goal_id} gate.pending {...}
   3. graph.interrupt() — thread suspends
   │
   ▼
cosign-api · sse multiplexer
   Browser subscribed to /stream/goals/{id}
   gate.pending event flows to browser
   │
   ▼
cosign-web · CosignGate modal renders
   User clicks [Cosign & implement]
   POST /goals/{id}/resume {decision: "approve"}
   │
   ▼
cosign-api · handler
   1. UPDATE interrupts SET resolved_at=NOW, decision='approve', actor_user_id=...
   2. INSERT audit_log (event=cosign, ...)
   3. gRPC: ResumeFromInterrupt(goal_id, {decision: "approve"})
   │
   ▼
cosign-worker · resume
   graph.Command(resume={decision:"approve"})
   │
   ▼
implementer_node (re-entered)
   1. Apply reviewer's suggested_changes
   2. Run tests in sandbox; iterate up to 2 times on failure
   3. commit + push via DockerDriver.commit_and_push
   4. github.post_comment on PR linking to cosign event
   │
   ▼
finalize_node → END
   UPDATE goals SET status='done', completed_at=NOW
   INSERT audit_log (event=goal_completed)
   PUBLISH goal.completed
```

### 3.2 Flow B — Issue → Critic Loop

```
Issue assigned to cosign[bot]
   │ webhook
   ▼
cosign-api · gateway/webhook
   verify, lookup installation, INSERT goals (type=issue_implement)
   │ gRPC: SubmitGoal
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
   │        - reads state.diff (empty round 1)      │
   │        - reads state.critic_feedback (empty r1)│
   │        - emits new diff + self_satisfaction    │
   │        - INSERT critic_iterations              │
   │        - PUBLISH stream: iteration.implementer │
   │   2. IF self_satisfaction >= threshold         │
   │         OR iteration >= max_iters: BREAK       │
   │   3. critic_node                               │
   │        - reads state.diff                      │
   │        - emits structured feedback             │
   │        - UPDATE critic_iterations              │
   │        - PUBLISH stream: iteration.critic      │
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
Browser ← SSE gate.pending ← cosign-api
   CosignGate renders with TranscriptViewer
   User cosigns
   POST /goals/{id}/resume
   │
   ▼
cosign-worker resumes
   IF repo has App installed → push branch + open PR via go-github
   ELSE → fork-mode (see §7.2)
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

## 5. Caching

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

### 7.1 GitHub App (own / installed repos)

**App scopes (minimum):**
- `contents:write` — clone, commit, push, fork
- `pull_requests:write` — create PRs, post comments
- `issues:write` — comment on issues, post status
- `metadata:read` — basic repo info
- `checks:write` — optional, for Cosign-as-a-check-run UX later

**Webhook events subscribed:**
- `pull_request.opened` → Flow A trigger
- `pull_request.synchronize` → re-run reviewer if `/cosign re-review` was previously posted
- `issues.assigned` → if assignee is `cosign[bot]`, trigger Flow B
- `issue_comment.created` → parse `/cosign <verb>` slash commands
- `installation.created` / `installation.deleted` → maintain `installations` table

**Slash commands:**
- `/cosign review` — manually trigger Flow A on a PR
- `/cosign work` — manually trigger Flow B on an issue
- `/cosign steer <text>` — inject mid-loop feedback (Flow B only)
- `/cosign cancel` — cancel a running goal on this PR/issue
- `/cosign status` — post a status comment

**HMAC verification:** every webhook payload is verified with `X-Hub-Signature-256` against the App's webhook secret. Mismatch → 401, no DB writes.

### 7.2 Fork-mode (upstream repos)

For repos the user does not own and where the Cosign App is not installed. Flow:

```
1. User submits goal targeting github.com/{upstream_owner}/{repo}
2. cosign-api checks: is repo in installations? NO
3. cosign-api checks: does user have a fresh OAuth token? NO → redirect to /auth/github/oauth
4. User completes OAuth (with scopes: public_repo + workflow)
5. cosign-api stores encrypted OAuth token on users row
6. cosign-worker uses USER'S OAuth token (not App token) to:
     a. POST /repos/{upstream_owner}/{repo}/forks → creates {user_login}/{repo}
     b. Clones the fork into the sandbox
     c. Runs the agent flow as normal
     d. Pushes branch to the user's fork
     e. POST /repos/{upstream_owner}/{repo}/pulls with head={user_login}:{branch}
          → opens the PR upstream, authored by the user
7. Cosign-api records the upstream PR URL on the goal and audit log
```

**Critical detail:** the PR is authored by the user (not by `cosign[bot]`), because the user's OAuth token is what opened it. This is correct behavior — the user is the one cosigning the contribution to an OSS project.

**Abuse mitigation:** fork-mode goals are rate-limited per user (default 5/hour, configurable). A repo allowlist can be set for public demo deployments to prevent the platform being abused to spam upstreams.

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
