# Cosign — Product Requirements Document

**Version:** 0.1.0-draft
**Team:** Tensor-Bloom
**Hackathon delivery date:** 2026-06-10
**Status:** Planning
**Last Updated:** 2026-06-02

---

## Table of Contents

1. [Product Vision](#1-product-vision)
2. [Problem Statement](#2-problem-statement)
3. [Goals and Success Metrics](#3-goals-and-success-metrics)
4. [User Personas](#4-user-personas)
5. [Competitive Positioning](#5-competitive-positioning)
6. [Core Feature Set](#6-core-feature-set)
7. [Out of Scope (v1)](#7-out-of-scope-v1)
8. [Open Questions and Decisions Log](#8-open-questions-and-decisions-log)

---

## 1. Product Vision

### 1.1 One-Line Definition

> **Cosign is a human-in-the-loop collaboration platform where AI agents review pull requests and work on issues, run a critic-agent loop to refine the work, and require a human cosign before any action ships.**

### 1.2 What Makes Cosign Different

Most AI dev tools today fall into three failure modes: they're either fully autonomous (and unsafe to point at a real repo), suggestion-only (and put all the work back on you), or comment-only (they review but never act). Cosign occupies the gap between them, anchored on four design choices:

1. **Cosign as a UX primitive.** Every side-effectful action — pushing code, opening a PR, posting a comment, merging — requires a literal human cosign gesture in the UI. The gate isn't a setting; it's the product.
2. **Critic-loop with a self-satisfaction score.** Issue work runs an implementer agent against a critic agent iteratively. The implementer emits a numeric self-satisfaction score each round. The loop exits when the score crosses a threshold OR a max-iteration cap is hit. Convergence is observable, not vibes-based.
3. **Iteration transcript as a first-class artifact.** Humans don't just see the final diff. They see every round of critic pushback and implementer revision — persisted, viewable in the UI, attached to the cosign payload. This is what makes "cosign" a meaningful gesture instead of a rubber stamp.
4. **Dual-mode GitHub integration.** A GitHub App for repos you own (webhook-driven, `/cosign` slash commands, agent acts as itself), AND an OAuth fork-and-PR flow for upstream OSS repos you don't own (agent pushes to your fork, opens PR upstream as you). Both shipped on day one.

### 1.3 Background

Cosign reuses architectural ideas from an internal reference design (Mergit) — multi-agent orchestration via LangGraph, sandboxed tool execution, multi-layer caching, capability-gated tool calls — but drops the blockchain layer entirely and reshapes the product around the two HITL flows in §6. The result is a much smaller surface to build (3 services instead of 8) and a sharper, more demoable product story.

---

## 2. Problem Statement

### 2.1 The False Choice in Today's AI Dev Tools

| Existing approach | Examples | Failure mode |
|---|---|---|
| Fully autonomous | Devin, Sweep (auto-merge mode), some autoGPT forks | Ships changes you didn't review. One wrong refactor can hose a service. Trust collapses on the first incident. |
| Suggestion-only | Cursor inline suggestions, GitHub Copilot, Aider in local-edit mode | Human does all the actual reviewing and merging. AI saves keystrokes, not decisions. |
| Comment-only review | CodeRabbit, Greptile, PR-Agent | Reviews PRs with useful comments but never *acts*. You still have to read the review, apply the suggestion, push the commit. |

None of these resolve the underlying tension: **developers want AI to do the work, but won't ship AI output without human verification — and verifying raw AI output is its own full-time job.**

### 2.2 What Cosign Does Differently

Cosign sits in the gap: **AI does the work, AI critiques itself, then a human cosigns a single structured artifact (review + iteration transcript + final diff) to unblock the action.**

The human's cognitive load drops from "read every line, decide if it's correct" to "skim the transcript, click cosign." The agent's autonomy drops from "merges things you didn't see" to "can't ship anything without your signature." Both sides win, and the gate is the product.

### 2.3 Concrete User Scenarios

These are the three scenarios Cosign is built to handle. Each is tied to which existing tool fails it and how Cosign succeeds.

**Scenario 1 — "Triage 47 dependabot PRs over the weekend."**
A maintainer comes back to a stack of dependency-bump PRs on a repo they own. Today: they merge them one by one, occasionally getting bitten by a breaking change. With Cosign: each PR is auto-reviewed by the reviewer agent on open (the App is installed, webhook fires); the maintainer skims the review summary in the Cosign UI, sees which ones the agent flagged as risky, cosigns the safe ones in bulk, and follows up on the risky ones individually. *Today's failure: CodeRabbit reviews each PR but the maintainer still has to click merge 47 times. Devin would auto-merge them and pray.*

**Scenario 2 — "Fix a typo and a broken link in a popular OSS README I don't own."**
A contributor notices a typo in a popular project's README. Today: clone, edit, fork, push, open PR — 10 minutes of context switching for a 1-line change, so they never bother. With Cosign: paste the repo URL, describe the change ("fix typo on line 47, update the broken Discord link"), grant OAuth on first run; Cosign forks the repo to the contributor's account, runs the implementer agent against the fork, surfaces the diff for cosign, opens the PR upstream from the fork — all under a minute. *Today's failure: Cursor and Aider can't touch upstream. CodeRabbit and Sweep require install permission they'll never get on a repo they don't own.*

**Scenario 3 — "Resolve a tagged `good-first-issue` while I'm in a meeting."**
A solo dev tags an issue `good-first-issue` in their own repo and assigns it to the Cosign bot before stepping into a 1-hour meeting. Cosign runs the implementer + critic loop in the background: implementer produces a fix (self-satisfaction 0.62), critic pushes back on edge cases, implementer revises (0.78), critic pushes back on test coverage, implementer adds tests (0.91 — over threshold, loop exits). When the dev gets out of the meeting, the cosign gate is waiting with the full iteration transcript and final diff. They skim and cosign; PR opens. *Today's failure: Devin would have shipped round 1 (the buggy version). Aider needs the dev sitting at the keyboard the whole time. CodeRabbit doesn't do issue-to-PR.*

---

## 3. Goals and Success Metrics

### 3.1 Hackathon Goals (by 2026-06-10)

| Goal | Success criterion |
|---|---|
| Working Flow A end-to-end | Open a PR on a test repo with the App installed → reviewer agent runs → human gate in UI → cosign → implementer pushes commit. |
| Working Flow B end-to-end | Assign an issue to the bot → implementer + critic loop runs (live SSE feed) → loop exits on self-satisfaction OR max-iter → human cosigns transcript + diff → PR opens. |
| Working fork-mode | Submit a goal against a repo the App is *not* installed on → OAuth fork-and-PR flow completes → upstream PR is open. |
| Caching demonstrably saves cost | Run the same goal twice; metrics show ≥50% reduction in LLM input-token spend on the second run. |
| 3–4 min recorded demo video | Hits all four innovation points in §1.2 in narrative order. |

### 3.2 Post-Hackathon Product Metrics

- **Human-approval rate** — fraction of agent outputs the user cosigns without revision. Target: >70% after tuning.
- **Critic-loop convergence iterations** — median number of implementer↔critic rounds before self-satisfaction threshold. Target: 2–3.
- **Time-to-cosign** — wall-clock from goal submission to gate ready for human. Target p50 <90s for Flow A, <5 min for Flow B.
- **Cache hit rate** — combined provider + Redis cache hits across all LLM calls. Target: >50%.
- **$/PR** — average LLM spend per shipped PR. Target: <$0.10 with caching, <$0.40 without.

---

## 4. User Personas

### 4.1 Developer (own repos)

Wants AI to triage and fix issues on repos they maintain. Installs the Cosign GitHub App on their account/org. Comfortable with `/cosign` slash commands in PR/issue comments. Will not ship un-reviewed AI code, but is happy to skim a transcript and cosign in seconds.

### 4.2 OSS Contributor (other people's repos)

Wants to contribute small fixes to upstream repos they don't own and can't install Apps on. Uses fork-mode: pastes a repo URL into the Cosign web UI, grants OAuth on first use, lets Cosign handle fork + branch + push + upstream PR.

### 4.3 Team Lead

Manages a team that uses Cosign on shared repos. Cares about the audit trail: which agent touched which file, which human cosigned which action, when. Wants the audit log queryable and exportable.

---

## 5. Competitive Positioning

Cosign vs adjacent tools across the six dimensions that matter for our positioning.

| Dimension | **Cosign** | Devin | Cursor | Aider | CodeRabbit | Sweep |
|---|---|---|---|---|---|---|
| **Human gate on side effects** | Required for every push/PR/merge | Optional / off by default | Manual (you press Cmd+S) | Manual (you commit) | None (review-only) | Optional |
| **Critic-loop with exit metric** | Yes (numeric self-satisfaction + max-iter) | No (single-shot agent) | No | No | No | No |
| **Iteration transcript visible** | Yes (UI + cosign payload + DB) | Partial (session log) | No | Local terminal only | No (single review comment) | No |
| **Upstream OSS contribution** | Yes (fork-mode + App both) | App-only | Local-only | Local-only | App-only | App-only |
| **Deploy model** | Self-host (Docker / k8s) | SaaS only | Local IDE | Local CLI | SaaS only | SaaS / self-host |
| **Openness** | Open source from day 1 | Closed | Closed | Open source | Closed | Open source |

---

## 6. Core Feature Set

### 6.1 Flow A — PR Review with Human Gate

Triggered when a PR opens on a repo with the Cosign App installed, or when someone comments `/cosign review` on an existing PR.

```
1. PR opened (webhook) OR /cosign review (comment)
        │
        ▼
2. cosign-api receives webhook, creates a Goal of type=pr_review
        │
        ▼
3. cosign-worker spawns reviewer agent in sandboxed container
        │
        ▼
4. Reviewer agent reads the diff + relevant context files,
   produces a structured review artifact:
     { summary, risk_score, per_file_comments, suggested_changes }
        │
        ▼
5. SSE event 'gate.pending' fires; web UI shows the review
   with a [Cosign & implement] / [Revise] / [Reject] choice
        │
        ▼
6. Human cosigns ────────────────────► implementer agent runs:
                                          - applies suggested_changes
                                          - runs tests in sandbox
                                          - opens a follow-up commit to the PR branch
                                          - posts a comment linking to the cosign transcript
   Human revises (with feedback) ─────► reviewer agent re-runs with feedback in prompt
   Human rejects ─────────────────────► goal marked cancelled, audit log written
```

**Key behaviors:**
- Implementer never pushes without a cosign on the review.
- Implementer's commit message references the cosign event ID for auditability.
- If the implementer's test run fails inside the sandbox, the implementer enters a self-recovery sub-loop (max 2 attempts) before surfacing the failure back to the human.

### 6.2 Flow B — Issue → Critic Loop

Triggered when a user assigns an issue to the Cosign bot in the GitHub UI, or comments `/cosign work` on an issue.

```
1. Issue assigned to bot (webhook) OR /cosign work (comment)
        │
        ▼
2. cosign-api receives webhook, creates a Goal of type=issue_implement
        │
        ▼
3. cosign-worker spawns implementer agent in sandboxed container,
   clones repo at default branch
        │
        ▼
4. ┌─── critic-loop subgraph ──────────────────────────────┐
   │  4a. Implementer reads issue + repo, produces diff      │
   │      + writes self-satisfaction score (0.0–1.0)         │
   │  4b. IF score >= threshold (default 0.85)               │
   │         OR iteration_count >= max_iters (default 5)     │
   │      THEN exit loop                                     │
   │      ELSE go to 4c                                      │
   │  4c. Critic agent reads diff + issue + repo,            │
   │      produces structured feedback:                      │
   │        { blocking_issues, suggestions, score }          │
   │  4d. Implementer reads critic feedback, revises diff,   │
   │      emits new self-satisfaction score; back to 4b      │
   └─────────────────────────────────────────────────────────┘
        │
        ▼
5. SSE event 'gate.pending' fires with full iteration transcript
   + final diff; web UI shows transcript viewer + cosign button
        │
        ▼
6. Human cosigns ──► cosign-worker pushes branch + opens PR
                     OR (fork-mode) opens PR upstream from fork
   Human revises ──► implementer re-runs with human feedback prepended
   Human rejects ──► goal marked cancelled
```

**Key behaviors:**
- Loop exit threshold and max-iters are configurable per-goal (defaults: 0.85, 5).
- The iteration transcript records: per-round prompt, per-round diff, per-round self-satisfaction score, per-round critic feedback. Stored in `critic_iterations` table, surfaced as one collapsible block per round in the UI.
- The human can manually inject feedback mid-loop via a "Steer" action that pauses the loop, accepts a text input, and resumes with the input prepended to the next implementer prompt.

### 6.3 Agent Roles

Three agent roles, deliberately collapsed from the reference design's four roles to keep the v1 surface small.

| Role | Responsibility | Default LLM |
|---|---|---|
| **Implementer** | Reads issue/PR, writes code, runs tests in sandbox, emits self-satisfaction score | Anthropic Claude Sonnet 4.6 |
| **Reviewer** | Reads diff, produces structured review artifact (summary, risk score, per-file comments, suggestions) | Anthropic Claude Sonnet 4.6 |
| **Critic** | Reads diff + issue, produces structured feedback (blocking issues, suggestions, score) | Groq Llama 3.3 70B (fast, cheap for iteration) |

Multi-provider routing with Redis-tracked health (primary → fallback chain) lives in the worker.

### 6.4 Tool Ecosystem

| Tool | Category | Notes |
|---|---|---|
| `github_ops` | Integration | Read repos/issues/PRs/files, post comments, create PRs, fork repos, push branches |
| `code_exec` | Execution | Run shell commands inside the sandbox container; 30s timeout per call |
| `file_ops` | Execution | Read/write/delete files inside the sandboxed repo workspace |
| `web_search` | Research | Brave or Serper API with Redis-cached results (1h TTL) |

All tool calls go through a capability check before execution (per-agent allowlist).

### 6.5 Human-in-the-Loop Interrupts

| Trigger | Payload | User actions |
|---|---|---|
| Reviewer agent finishes (Flow A) | Review artifact | Cosign & implement / Revise w/ feedback / Reject |
| Critic-loop exits (Flow B) | Iteration transcript + final diff | Cosign & open PR / Revise w/ feedback / Reject |
| Implementer detects dangerous-pattern in own output (e.g., deleting >50% of a file, modifying CI config, secrets in diff) | Snippet + reason | Allow / Block |
| `/cosign steer` comment during a running loop | Current state | Pause + accept text feedback + resume |

### 6.6 Iteration Transcript (First-Class Entity)

The transcript is **the** artifact a human reviews to cosign. It is:

- **Persisted** in the `critic_iterations` table (one row per round).
- **Streamed live** to the web UI via SSE during the loop.
- **Viewable post-hoc** as a collapsible per-round block: prompt, diff, self-satisfaction score, critic feedback.
- **Attached to the cosign event payload** so the audit log records exactly what the human saw at cosign time.
- **Exportable as a single JSON file** for offline review or sharing.

This is the differentiator that makes cosigning a meaningful gesture instead of a rubber stamp.

---

## 7. Out of Scope (v1)

Explicitly **not** part of the 2026-06-10 delivery:

- Blockchain / on-chain identity / on-chain proofs / reputation NFTs (the Mergit reference's main thrust — fully removed).
- Semantic LLM cache (FAISS / pgvector / embedding-based query similarity) — deferred; covered only by L2 prompt cache + 4 Redis caches in v1.
- Multi-tenancy with per-tenant billing and quotas.
- Self-hosted LLM inference (vLLM / SGLang) — managed APIs only in v1.
- Fully-autonomous mode (no human gate). Cosign is deliberately not building this; it would defeat the product's positioning.
- Kubernetes manifests. Architecture is k8s-friendly (stateless services, env-var config, swappable sandbox driver), but actual manifests are a post-hackathon port (~1 day).
- Mobile app, browser extension, IDE integration.

---

## 8. Open Questions and Decisions Log

| # | Question | Status | Decision / Notes |
|---|---|---|---|
| 1 | Project name | **Decided** | Cosign |
| 2 | Backend stack for the API service | **Decided** | Go (not Rust). Removing chain removed Rust's only must-have (alloy). Go ships faster on the 8-day budget. |
| 3 | Service topology | **Decided** | 3 services (cosign-api in Go, cosign-worker in Python, cosign-web in React/Next), modular monolith pattern with clean internal package boundaries. Extract to more services post-hackathon if needed. |
| 4 | GitHub integration scope | **Decided** | App + fork-mode both shipped by 10 Jun. |
| 5 | Sandbox strategy | **Decided** | Docker-per-task with swappable `SandboxDriver` interface (k8s pod driver added post-hackathon). |
| 6 | Caching scope for v1 | **Decided** | L2 provider prompt cache + 4 Redis caches (LLM exact-hash, tool output, plan, GitHub ETag). No semantic cache in v1. |
| 7 | Critic-loop default max iterations | **Open** | Default 5 proposed; tune after Day 5 once we see real convergence behavior. |
| 8 | Critic-loop default self-satisfaction threshold | **Open** | Default 0.85 proposed; tune empirically. |
| 9 | Default LLM provider routing | **Open** | Proposed: Anthropic Sonnet primary for implementer/reviewer, Groq Llama for critic; fallback to OpenAI on rate-limit. Confirm after Day 4. |
| 10 | GitHub App scopes | **Open** | Minimum required: contents:write, pull_requests:write, issues:write, metadata:read, checks:write. Finalize on Day 2. |
| 11 | Storage for the iteration transcript export JSON | **Open** | Probably just return as a download from the API; revisit if file sizes get large. |
| 12 | Web UI framework | **Open** | Next.js 15 App Router proposed (single TS app, SSR + client). Alternative: Vite + React + a thin BFF. Confirm Day 1 PM. |
| 13 | Rate-limit / abuse handling for fork-mode (anyone with OAuth can target any public repo) | **Open** | Initial plan: per-user goal-rate limit + repo allowlist for the public demo. Revisit before launch. |

---

*This document is the source of truth for Cosign's product scope. Implementation detail lives in [ARCHITECTURE.md](./ARCHITECTURE.md); the build schedule lives in [ROADMAP.md](./ROADMAP.md).*
