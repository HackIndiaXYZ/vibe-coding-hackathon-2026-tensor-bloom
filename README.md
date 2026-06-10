# Cosign

> **AI drafts the work. An AI critic refines it. You cosign.**
> Reviews and pull requests ship **under your name** on GitHub — never a bot's.

**Built by [Tensor-Bloom](https://github.com/HackIndiaXYZ/vibe-coding-hackathon-2026-tensor-bloom) for HackIndia Vibe Coding Hackathon 2026.**

[![Live demo](https://img.shields.io/badge/demo-live-brightgreen.svg)](https://cosign.34-131-58-38.sslip.io)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## What it does (and how)

Cosign is a **human-in-the-loop web app** for code review and issue→PR work. You point it at any GitHub PR or issue and click one of two buttons — the agents do the work, and **you cosign once** before anything ships, attributed to you via your OAuth token (no `cosign[bot]`).

### Flow A — Review a PR
```
[Review with Cosign] → reviewer agent reads the PR diff (GitHub API)
   → drafts a structured review (summary · risk · per-file comments · asks · praise)
   → you edit it inline → cosign → it posts on the PR AS YOU
```
**How:** `plan → reviewer → gate`. The reviewer reads the diff over the GitHub API and the `diff_analysis` tool, then an LLM drafts the review; cosign-api posts it with your OAuth token. No sandbox needed.

### Flow B — Resolve an issue → PR
```
[Resolve with Cosign] → implementer ⇄ critic loop inside a sandbox container
   round 0: implementer edits files (self-satisfaction 0.62) → critic feedback
   round 1: implementer revises (0.78)                       → critic feedback
   round 2: implementer revises (0.91) → crosses threshold   → exits
   → you review the full transcript + final diff → cosign → PR opens AS YOU
```
**How:** the worker clones your repo into a **fresh per-task Docker sandbox**, builds a `repo_map` (tree-sitter), then runs a **LangGraph** `plan → (implementer ⇄ critic) → gate → finalize` loop. The implementer edits real files (`file_ops`), runs `test_runner`/`lint`, and the diff is the real `git diff`. The loop runs to a numeric self-satisfaction threshold (or max-iter), you cosign, and the branch is pushed + PR opened with your token.

### What makes it different
- **The gate is the product** — every side-effect (push, PR, review) needs a literal human cosign.
- **An AI critic drives iteration, not you** — you enter *once*, at the end, with the whole transcript in front of you.
- **Live activity stream + revisions** — watch each agent fire and each tool call stream in (SSE), and browse every revised version of the code with a round-to-round diff compare.
- **Posted as you** — on repos you own *and* any public upstream repo, via OAuth.
- **Cost-transparent + per-role LLM routing** — a live `$/goal` ledger; cheap models for planning/criticism, premium reserved for the value-critical steps. Bring your own key per role, or use the shared demo key.

---

## 🔗 Live demo

**[https://cosign.34-131-58-38.sslip.io](https://cosign.34-131-58-38.sslip.io)**

1. **Sign in with GitHub** (top-right).
2. **Resolve an issue** — paste an issue URL on **a repo you own** → watch the implementer⇄critic loop run live → cosign → a PR opens on your repo.
3. **Review a PR** — paste any PR URL → edit the drafted review → cosign → it posts as you.
4. **Settings** — a shared **Anthropic Haiku** key is provided (capped at **$0.50/user**); add your own provider key to remove the cap and pick any model per role.

---

## Run it locally

**Prerequisites:** Docker + Docker Compose v2. (A GitHub OAuth App and LLM keys are optional — without them it runs on a keyless **mock** LLM.)

```bash
git clone <this-repo> cosign && cd cosign

# 1. (optional) point a GitHub OAuth App's callback at:
#    http://localhost:8080/auth/github/callback
#    and put its client id/secret + an ANTHROPIC_API_KEY/GROQ_API_KEY in infra/.env

# 2. one command: builds the sandbox image, starts Postgres+Redis, runs migrations,
#    builds + starts api + worker + web
./scripts/setup-dev.sh --with-app

# → http://localhost:3000
```

`scripts/setup-dev.sh` also generates the JWT + AES keys (`scripts/gen-keys.sh`) and is **re-run-safe** (migration ledger). Configuration lives in `infra/.env` (see `infra/.env.example`):

| Var | Purpose |
|---|---|
| `GITHUB_OAUTH_CLIENT_ID` / `_SECRET` | sign-in + acting as the user |
| `ANTHROPIC_API_KEY` / `GROQ_API_KEY` | LLM providers |
| `LLM_ROUTING_CONFIG` | `config/llm-routing.yaml` (real) or `config/llm-routing.mock.yaml` (keyless) |
| `DEMO_USER_CAP_USD` | per-user $ cap on the shared key (`0` = disabled) |

Rebuild after a change: `docker compose -f infra/docker-compose.yml --profile app up -d --build <service>`.
Deploy to a public URL on GCP: see **[`docs/DEPLOY_GCP.md`](docs/DEPLOY_GCP.md)** (single Compute Engine VM + Caddy auto-TLS).

---

## Architecture

A **3-service modular monolith** behind Caddy. The worker spawns one ephemeral, network-isolated Docker container per agent task.

```
                         Browser (HTTPS + SSE)
                                │
                          Caddy (TLS, reverse proxy)
                     /api/* │                 │ /*
                            ▼                 ▼
        ┌───────────────────────────┐   ┌──────────────────────────┐
        │ cosign-api  (Go·chi·sqlc) │   │ cosign-web (Next.js 16)  │
        │ OAuth/JWT · REST · SSE    │   │ Engineered-Blueprint UI  │
        │ identity gRPC · budget    │   │ live feed · revisions    │
        └─────────────┬─────────────┘   └──────────────────────────┘
                      │ gRPC (orchestration)
                      ▼
        ┌───────────────────────────────────────────────┐
        │ cosign-worker  (Python · LangGraph · LiteLLM) │
        │ plan → reviewer | implementer⇄critic → gate   │
        │ tools: github · code · file_ops · test_runner │
        │        lint · repo_map · diff_analysis        │
        │ per-role LLM router (+BYO keys) · SandboxDriver│
        └───────┬───────────────────────────────┬───────┘
                │ asyncpg / redis               │ docker.sock
                ▼                                ▼
        PostgreSQL 16   Redis 7 (SSE streams)   per-task sandbox containers
                                                (cosign_sandbox_net, egress-limited)
```

**Service responsibilities**
- **cosign-api (Go)** — the only public service: GitHub OAuth + RS256 JWT, REST, the SSE multiplexer (fans Redis streams to browsers), the identity gRPC server (capability checks, hands the worker the user's decrypted OAuth token + per-user LLM keys), the audit log, and the per-user **budget gate**.
- **cosign-worker (Python)** — the brain: LangGraph state machine for both flows, all agent roles + tools, the `SandboxDriver` (Docker-per-task), and the **per-role LLM router** (LiteLLM) — every model call goes through one place, with precedence `user override → user default → operator config → fallback → mock`.
- **cosign-web (Next.js 16)** — the dark "Engineered Blueprint" UI: the cosign gate, inline review editor, the live **activity stream** (agent + tool-call events over SSE), the **revisions** browser, the cost ledger, and `/settings` (per-role model picker + BYO keys + budget).

**Per-role LLM routing** (`config/llm-routing.yaml`, operator-set; users override in `/settings`):

| Role / tool | Default | Why |
|---|---|---|
| `plan_node`, `implementer`, `reviewer`, `critic`, `diff_analysis` | Anthropic Claude Haiku (demo) | cheap → fits the per-user budget; swap any role to Sonnet/Groq/your key |
| `repo_map`, `lint`, `test_runner` | *(no LLM)* | deterministic local code |

**Key flows of data**
- **Auth:** browser → OAuth → api stores the token AES-GCM-encrypted; the worker fetches+decrypts it over gRPC only at goal time, acts as the user on GitHub, never logs it.
- **Live updates:** worker → Redis stream `stream:goal:{id}` → api SSE → browser (the activity feed replays full history on reconnect).
- **Cost/budget:** every LLM call records `messages.cost_usd` (+ `operator_funded`); `$/goal` is a `GROUP BY`, and per-user shared-key spend gates the demo budget.

**Data model** (PostgreSQL): `users`, `goals`, `tasks`, `messages`, `critic_iterations` (the transcript), `interrupts` (HITL gates), `audit_log`, `user_llm_settings` + `user_provider_keys` (BYO routing/keys). Migrations in `infra/postgres/migrations/`.

---

## Tech stack

| Layer | Stack |
|---|---|
| API | Go 1.26 · chi · sqlc · grpc-go · go-redis · golang-jwt · go-github |
| Worker | Python 3.12 · uv · FastAPI · LangGraph · LiteLLM · asyncpg · aiodocker · tree-sitter |
| Web | Next.js 16 (App Router) · React 19 · TypeScript · Tailwind 4 · framer-motion |
| Data | PostgreSQL 16 (+ pgvector) · Redis 7 (streams) |
| Sandbox | Docker (per-task, egress-restricted) · swappable `SandboxDriver` |
| LLM | Anthropic · Groq · OpenAI via LiteLLM, per-role routing + BYO keys |
| Infra | Docker Compose v2 · Caddy 2 (auto-TLS) · GCP Compute Engine |

---

## Documentation

Design docs on the [`docs` branch](https://github.com/HackIndiaXYZ/vibe-coding-hackathon-2026-tensor-bloom/tree/docs/docs): **PRD** (product + competitive positioning), **ARCHITECTURE** (services, schema, caching, sandbox), **ROADMAP**, **WORKSTREAMS**. Deployment guide: [`docs/DEPLOY_GCP.md`](docs/DEPLOY_GCP.md).

## Team & License

**Tensor-Bloom** · HackIndia Vibe Coding Hackathon 2026 · [MIT](LICENSE)
