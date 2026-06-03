# Cosign

> **AI ghostwriter for code reviews and pull requests.**
> AI drafts the work. You edit. You cosign. The output ships **under your name** on GitHub — not a bot's.

**Built by [Tensor-Bloom](https://github.com/HackIndiaXYZ/vibe-coding-hackathon-2026-tensor-bloom) for HackIndia Vibe Coding Hackathon 2026 · Submission target: 2026-06-10**

[![Status: Planning](https://img.shields.io/badge/status-planning-yellow.svg)](docs/ROADMAP.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Docs: PRD](https://img.shields.io/badge/docs-PRD-blue.svg)](https://github.com/HackIndiaXYZ/vibe-coding-hackathon-2026-tensor-bloom/blob/docs/docs/PRD.md)
[![Docs: ARCHITECTURE](https://img.shields.io/badge/docs-ARCHITECTURE-blue.svg)](https://github.com/HackIndiaXYZ/vibe-coding-hackathon-2026-tensor-bloom/blob/docs/docs/ARCHITECTURE.md)

---

## What is Cosign?

Cosign is a **human-in-the-loop web app for code reviews and issue → PR work.** A developer opens Cosign, points it at any PR or any issue (on a repo they own, or any public repo), and clicks one of two buttons:

- **[Review with Cosign]** — an AI reviewer agent reads the PR and drafts a structured review in an inline editor. The user edits the draft to their voice, clicks Cosign, and the review posts on the PR **as the user** via OAuth — no bot account on the public record.
- **[Resolve with Cosign]** — an implementer agent and a critic agent iterate on the issue inside a sandboxed container, refining the diff until a numeric self-satisfaction score crosses a threshold (or a max-iteration cap is hit). The user sees the full iteration transcript, cosigns once at the end, and the PR opens **authored by the user**.

The whole system is engineered around one principle: **AI amplifies your voice. AI is invisible to the rest of GitHub.**

---

## What makes Cosign different

Most AI dev tools fall into three patterns:
- **Autonomous bots** (Devin, Sweep) — ship code you didn't review.
- **Webhook-driven review bots** (CodeRabbit, Greptile, Qodo) — post reviews as their bot account, on every PR.
- **Inline IDE assistants** (Cursor, Copilot, Aider) — useful but local-only.

Cosign sits in a different category, anchored on six design choices:

| # | Design choice | Why it matters |
|---|---|---|
| 1 | **Cosign as a UX primitive** | Every side-effectful action (push, PR, comment, review) requires a literal human cosign gesture. The gate is the product. |
| 2 | **AI critic drives the iteration loop — not you** | Copilot makes *you* the critic across rounds (bot pushes → you comment → repeat). Cosign runs an AI critic in a loop *inside the worker* until convergence. You enter **once**, at the end. 3 rounds = 3 context switches in Copilot, 1 in Cosign. |
| 3 | **Iteration transcript as a first-class artifact** | You don't just see the final diff — you see every round of critic pushback and implementer revision. That's the basis for cosigning meaningfully instead of rubber-stamping. |
| 4 | **User-initiated, not webhook-driven** | The agent runs because you clicked, not because GitHub fired an event. No bot lurking on your PRs. |
| 5 | **Posted as you, on any public repo** | Reviews/PRs are authored by the invoking user via OAuth — never a `cosign[bot]` account. Works on repos you own (App-installed) AND any public upstream repo (via OAuth fork-and-PR). |
| 6 | **Cost-efficient by design** | Multi-layer caching (>50% hit-rate target) + per-role LLM routing (cheap models for planning/criticism, premium for implementation). **Target: <$0.10 per shipped PR.** ~3–6× cheaper than running everything through a single premium model. |

For the full pitch + competitive analysis: [PRD §5 — Competitive Positioning](https://github.com/HackIndiaXYZ/vibe-coding-hackathon-2026-tensor-bloom/blob/docs/docs/PRD.md#5-competitive-positioning).

---

## Two flows at a glance

```
Flow A — User-Initiated PR Review
  User clicks [Review with Cosign] on any PR
       │
       ▼
  Reviewer agent runs in sandbox → drafts a structured review
       │
       ▼
  Inline editor surfaces the draft → user edits → user cosigns
       │
       ▼
  Review posts on the PR, authored by the user (OAuth, not a bot)


Flow B — User-Initiated Issue → PR
  User clicks [Resolve with Cosign] on any issue (own or upstream)
       │
       ▼
  Implementer ↔ Critic loop in sandbox:
    round 0: implementer diff (score 0.62) → critic feedback
    round 1: implementer revises (0.78)    → critic feedback
    round 2: implementer revises (0.91)    → exits loop
       │
       ▼
  TranscriptViewer surfaces every round → user cosigns
       │
       ▼
  PR opens on GitHub, authored by the user
  (own repo direct; upstream repo via OAuth fork-and-PR)
```

---

## Architecture at a glance

3-service modular monolith. Code-level detail in [ARCHITECTURE.md](https://github.com/HackIndiaXYZ/vibe-coding-hackathon-2026-tensor-bloom/blob/docs/docs/ARCHITECTURE.md).

```
                 Browser  (HTTPS + SSE)
                     │
                     ▼
    ┌────────────────────────────────────┐
    │ cosign-api  (Go · chi · sqlc)      │
    │ gateway · identity · reputation    │
    └────────────────┬───────────────────┘
                     │ gRPC
                     ▼
    ┌────────────────────────────────────┐
    │ cosign-worker  (Python · LangGraph)│
    │ orchestration · tools · sandbox    │
    │ LLM router (per-role) · 5-layer cache │
    └────────────────┬───────────────────┘
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
    PostgreSQL 16              Redis 7
    + pgvector               + Streams
                             + Sorted sets

    cosign-web  (Next.js 15 · React 19 · Tailwind)  ←  served separately
```

**Per-role LLM routing example** (operator-configured in `config/llm-routing.yaml`):

| Role | Model | Why |
|---|---|---|
| `plan_node` | Claude Haiku 4.5 | Task decomposition — cheap model is plenty |
| `critic` | Groq Llama 3.3 70B | Fast iteration; fires N times per goal |
| `implementer` | Claude Sonnet 4.6 | Value-critical; the actual code |
| `reviewer` | Claude Sonnet 4.6 | Value-critical; the user's voice |
| `tools.lint`, `tools.test_runner`, `tools.repo_map` | *(no LLM)* | Deterministic local code |

---

## Documentation

All design and planning docs live on the [`docs` branch](https://github.com/HackIndiaXYZ/vibe-coding-hackathon-2026-tensor-bloom/tree/docs/docs) (will be merged to `main` once code lands):

| Doc | Purpose |
|---|---|
| [PRD.md](https://github.com/HackIndiaXYZ/vibe-coding-hackathon-2026-tensor-bloom/blob/docs/docs/PRD.md) | Product: vision, problem, scenarios, features, competitive positioning, decision log |
| [ARCHITECTURE.md](https://github.com/HackIndiaXYZ/vibe-coding-hackathon-2026-tensor-bloom/blob/docs/docs/ARCHITECTURE.md) | Engineering: services, schemas, caching, sandbox, GitHub integration, deployment |
| [ROADMAP.md](https://github.com/HackIndiaXYZ/vibe-coding-hackathon-2026-tensor-bloom/blob/docs/docs/ROADMAP.md) | Delivery: 8-day day-by-day plan, demo script, cut lines |
| [WORKSTREAMS.md](https://github.com/HackIndiaXYZ/vibe-coding-hackathon-2026-tensor-bloom/blob/docs/docs/WORKSTREAMS.md) | Team: per-workstream briefings (Go / Python / Frontend / Docker) for parallel execution |

---

## Tech stack

| Layer | Stack |
|---|---|
| API service | Go 1.23 · chi · sqlc · grpc-go · go-redis · jwt · go-github |
| Worker | Python 3.12 · uv · FastAPI · LangGraph · LiteLLM · asyncpg · aiodocker · tree-sitter |
| Web | Next.js 15 (App Router) · React 19 · TypeScript · Tailwind 4 · Shadcn |
| Data | PostgreSQL 16 (+ pgvector) · Redis 7 |
| Sandbox | Docker (per-task, network-isolated) · `SandboxDriver` interface for future k8s |
| LLM | Anthropic Claude (Sonnet + Haiku) · Groq (Llama 3.3 70B) · OpenAI (fallback) via LiteLLM |
| Infra | Docker Compose v2 · Caddy 2 (TLS) · GitHub App + OAuth |

---

## Status

This is a hackathon project under active 8-day build (2026-06-02 → 2026-06-10).

- ✅ Day 1 — Docs + planning complete (PRD, ARCHITECTURE, ROADMAP, WORKSTREAMS shipped)
- ⏳ Day 2 — Scaffolding + GitHub App + OAuth
- ⏳ Day 3 — Sandbox driver + first implementer agent
- ⏳ Day 4 — Flow A end-to-end
- ⏳ Day 5 — Flow B critic loop
- ⏳ Day 6 — Fork-mode for upstream repos
- ⏳ Day 7 — Caching + per-role routing + cost dashboard
- ⏳ Day 8 — UI polish + deploy to demo VM + record demo video
- 🎯 Day 9 (Jun 10) — Hackathon submission

Full breakdown: [ROADMAP.md](https://github.com/HackIndiaXYZ/vibe-coding-hackathon-2026-tensor-bloom/blob/docs/docs/ROADMAP.md)

---

## Demo

A recorded demo video will be linked here on Day 8 (2026-06-09). The demo walks through:

1. **Flow A** — review a PR, edit the AI draft, cosign, review posts as the user
2. **Flow B** — resolve an issue, watch critic loop converge live, cosign, PR opens as the user
3. **Fork-mode** — work on an upstream public repo via OAuth fork + upstream PR
4. **Cost story** — `/cost` dashboard showing ~6× savings via per-role routing + caching

Demo script: [ROADMAP §Demo Script](https://github.com/HackIndiaXYZ/vibe-coding-hackathon-2026-tensor-bloom/blob/docs/docs/ROADMAP.md#demo-script-day-8-recording-target--3-to-4-minutes)

---

## Quick start

> Will be updated when code lands (Day 8). Initial dev setup will be:

```bash
git clone https://github.com/HackIndiaXYZ/vibe-coding-hackathon-2026-tensor-bloom.git cosign
cd cosign
cp infra/.env.example .env
# fill in: GITHUB_APP_*, JWT_*, ANTHROPIC_API_KEY, GROQ_API_KEY
./scripts/setup-dev.sh
# → Cosign running at http://localhost:3000
```

---

## Team

**Tensor-Bloom** · HackIndia Vibe Coding Hackathon 2026

Repo: [github.com/HackIndiaXYZ/vibe-coding-hackathon-2026-tensor-bloom](https://github.com/HackIndiaXYZ/vibe-coding-hackathon-2026-tensor-bloom)

---

## License

[MIT](LICENSE)
