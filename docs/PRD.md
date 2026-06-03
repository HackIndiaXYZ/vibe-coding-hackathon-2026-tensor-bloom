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

Most AI dev tools today fall into three failure modes: they're either fully autonomous (and unsafe to point at a real repo), suggestion-only (and put all the work back on you), or comment-only (they review but never act). Cosign occupies the gap between them, anchored on six design choices:

1. **Cosign as a UX primitive.** Every side-effectful action — pushing code, opening a PR, posting a comment, merging — requires a literal human cosign gesture in the UI. The gate isn't a setting; it's the product.
2. **An AI critic drives the iteration loop — not you.** Competing tools (Copilot Coding Agent, Sweep) make *you* the critic across rounds: bot pushes → you read → you comment → bot pushes again. Every round is your context switch. Cosign runs an implementer ↔ critic-agent loop *inside the worker* to convergence (numeric self-satisfaction threshold OR max-iter cap); you enter **once**, at the end, with the full transcript in front of you. 3 rounds = 3 context switches in Copilot, 1 in Cosign.
3. **Iteration transcript as a first-class artifact.** Humans don't just see the final diff. They see every round of critic pushback and implementer revision — persisted, viewable in the UI, attached to the cosign payload. This is what makes "cosign" a meaningful gesture instead of a rubber stamp.
4. **User-initiated, not webhook-driven.** Cosign is a **web app**, not a bot. The user opens the Cosign UI, picks a PR to review or an issue to resolve, and clicks a button. The agent runs because the user asked it to — not because a webhook fired in the background. This is the opposite of CodeRabbit / Sweep / PR-Agent, which auto-react to GitHub events.
5. **Posted as you, on any public repo. Private iteration, clean public artifact.** Every review / comment / PR Cosign creates is authored by the invoking user via their OAuth — never by a `cosign[bot]` account — on repos you own AND on any public upstream repo (via fork-and-PR). The implementer ↔ critic iteration happens *inside the worker*; the public PR shows one clean diff in your name, not a stream of bot commits. Competitors (Copilot Coding Agent, Devin, CodeRabbit) either post as a bot, leak iteration as public commits, or require App install on the target repo.
6. **Cost-efficient by design — multi-layer caching + per-role model routing.** A multi-agent product runs dozens of LLM calls per goal; cost can spiral fast. Cosign attacks this two ways: (a) **5-layer caching** — provider prompt cache (90% off cached input tokens), Redis LLM exact-hash cache, tool output cache, plan cache, GitHub ETag cache — drives a target **>50% hit rate**; (b) **per-role / per-tool LLM routing** — operators map each role (`implementer`, `reviewer`, `critic`, `plan_node`) to its own provider + model + API key, so cheap workloads use cheap models (Groq Llama / GPT-4o-mini / Claude Haiku for planning and criticism) while expensive workloads (Sonnet for implementation) only fire when needed. Target cost: **<$0.10 per shipped PR with caching, ~3–6× cheaper than competitors that route everything through a single premium model.**

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

Three scenarios that drive the v1 product. Each is **user-initiated from the Cosign UI** (no bot, no webhook auto-trigger) and each has a clear differentiator vs the current tools.

**Scenario 1 — "Help me review a contributor's PR on my own repo."**
A maintainer opens a contributor's PR. Their actual job here is *to review and leave constructive suggestions*, not to merge. Today: they read 600 lines of diff, mentally simulate the impact, write a comment, ask for changes, wait, re-review — repeat. With Cosign: from the Cosign UI, they click "Review with Cosign" on the PR. The reviewer agent reads the diff + relevant repo context and produces a draft review (summary, risk score, per-file suggestions, asks). The maintainer reads the draft inline, edits any wording they disagree with, cosigns — and Cosign posts the review on the PR as the maintainer (using the user's OAuth token, **never** as a generic bot). The maintainer is still the reviewer; Cosign is their drafting assistant.
> *Vs CodeRabbit / Greptile / PR-Agent:* those post AI review comments **as a bot**, automatically, on every PR — so the human voice is replaced, not amplified. **Cosign is the opposite: the human is always the named reviewer; AI is invisible to the contributor.** That's a fundamentally different positioning.

**Scenario 2 — "I'm an OSS contributor and I want AI help reviewing PRs on a repo I contribute to (but don't own)."**
An active OSS contributor sees a fresh PR on a project they regularly contribute to but don't maintain. They want to leave a thoughtful review — but they're skimming on a phone. From Cosign: they paste the PR URL, click "Review with Cosign", grant OAuth on first use. The reviewer agent runs against the PR diff. The contributor reads the draft, tweaks two lines they want phrased more politely, cosigns. Cosign posts the review as them via OAuth — no GitHub App install on the upstream repo required.
> *Vs every competitor:* CodeRabbit / Sweep / Greptile **cannot operate on a repo where their App isn't installed.** Cursor / Aider are local-IDE tools and don't do PR review. **Cosign is the only tool that lets a contributor leverage AI to author a review on any public repo, attributed to them.**

**Scenario 3 — "There's an issue (on my repo or someone else's) I want to close by opening a PR."**
A dev sees an issue — could be on their repo or any public repo — that they could fix in ~30 minutes if they had the time. From Cosign: they paste the issue URL (or pick it from their inbox if it's their repo), click "Resolve with Cosign", add any context ("the fix should also update the tests under tests/foo/"). The implementer + critic loop runs: round 0 implementer (self-satisfaction 0.62), critic feedback, round 1 (0.78), critic feedback, round 2 (0.91 — over threshold, loop exits). The dev sees the iteration transcript + final diff in the cosign gate, skims, cosigns. Own repo → PR opens directly; not their repo → Cosign forks to the dev's account first, then opens upstream from the fork. **PR is authored by the dev**, not by a bot.
> *Vs every competitor:* **Devin** does this autonomously and ships a buggy round-0 version; you find out the PR is wrong after the fact. **Aider** needs the dev at the keyboard the whole time. **Sweep** requires App install (only own/installed repos). **CodeRabbit** doesn't do issue→PR at all. Cosign is the only option that combines: user-initiated → critic-loop convergence → human cosign → works on any public repo → attributed to the user.

---

## 3. Goals and Success Metrics

### 3.1 Hackathon Goals (by 2026-06-10)

| Goal | Success criterion |
|---|---|
| Working Flow A end-to-end | User clicks [Review with Cosign] on a PR in the UI → reviewer agent runs → draft surfaces in inline editor → user edits + cosigns → review posts on the PR as the user. |
| Working Flow B end-to-end | User clicks [Resolve with Cosign] on an issue in the UI → implementer + critic loop runs (live SSE feed) → loop exits on self-satisfaction OR max-iter → user cosigns transcript + diff → PR opens authored by the user. |
| Working fork-mode | User picks an issue on a repo not in their installations → OAuth fork-and-PR flow completes → upstream PR opens from the user's fork. |
| Caching demonstrably saves cost | Run the same goal twice; `/metrics` shows ≥50% reduction in LLM input-token spend on the second run. Live cost-per-goal counter visible in the UI. |
| Per-role model routing works | Operator config maps `plan_node` → cheap model (Haiku/Llama), `implementer` → premium (Sonnet); UI cost breakdown shows planning at <10% of implementation spend on the same goal. |
| 3–4 min recorded demo video | Hits all six innovation points in §1.2 in narrative order. |

### 3.2 Post-Hackathon Product Metrics

- **Human-approval rate** — fraction of agent outputs the user cosigns without revision. Target: >70% after tuning.
- **Critic-loop convergence iterations** — median number of implementer↔critic rounds before self-satisfaction threshold. Target: 2–3.
- **Time-to-cosign** — wall-clock from goal submission to gate ready for human. Target p50 <90s for Flow A, <5 min for Flow B.
- **Cache hit rate** — combined provider + Redis cache hits across all LLM calls. Target: >50%.
- **$/PR** — average LLM spend per shipped PR. Target: **<$0.10 with caching + routing**, <$0.40 without. (Single-model Sonnet routing of a 3-round Flow B goal benchmarks at ~$0.45.)
- **Cost-mix ratio** — spend on cheap models (plan / critic) ÷ spend on premium models (implementer / reviewer). Target: <0.15 (cheap models do most of the bulk work; premium models are reserved for the value-critical steps).

---

## 4. User Personas

### 4.1 Maintainer (own repos)

Reviews PRs and triages issues on repos they maintain. Wants AI to help draft thorough reviews and to draft fixes for issues — but always as their assistant, with their name on the output. Connects their repos to Cosign via the GitHub App so Cosign can post on their behalf. Will never ship un-reviewed AI code, but happy to cosign in seconds after skimming.

### 4.2 OSS Contributor (other people's repos)

Active contributor to several upstream repos they don't own and can't install Apps on. Uses Cosign as a personal AI co-pilot: paste a PR URL to draft a review, or paste an issue URL to draft a fix. OAuth-authorized once; from then on Cosign acts as the contributor on any public repo — posting reviews, opening forks, opening upstream PRs, all attributed to the contributor.

### 4.3 Team Lead

Manages a team that uses Cosign on shared repos. Cares about the audit trail: which user invoked which agent on which PR/issue, which output they cosigned, when. Wants the audit log queryable and exportable.

---

## 5. Competitive Positioning

Cosign vs adjacent tools across the seven dimensions that matter for our positioning.

| Dimension | **Cosign** | Copilot Coding Agent | Devin | CodeRabbit | Sweep | Cursor / Aider |
|---|---|---|---|---|---|---|
| **Trigger model** | **User-initiated from UI** (you click) | User-assigned (issue → @copilot) | User-delegated (task → Devin) | Webhook auto-trigger | Webhook auto-trigger | Inline / CLI |
| **Output attributed to** | **The user** (via their OAuth) | `copilot-swe-agent[bot]` | The Devin bot account | A bot account | A bot account | The user (local edits) |
| **Who drives the iteration loop** | **AI critic agent** (until self-satisfaction or max-iter) | **You** (you comment, bot pushes, repeat) | Single-shot | N/A (single review) | You (you comment, bot pushes) | You |
| **Human gate on side effects** | Required for every push/PR/comment/review | Optional / merge gate only | Optional | None (auto-posts) | Optional | Manual (Cmd+S / commit) |
| **Iteration is visible to outsiders** | No (private in your UI) | Yes (every round is a public commit on the PR) | Partial (session log) | N/A | Yes | N/A (local) |
| **What you see at decision time** | Final artifact **+ iteration transcript with reasoning** | Final PR only | Final PR + session log | Final review comment | Final PR | Local diff |
| **Works on repos you don't own** | Yes (OAuth fork-and-PR + OAuth review-on-behalf) | App-only | App-only | App-only | App-only | Local-only |
| **Multi-layer caching** | **5 layers** (provider prompt + 4 Redis) → >50% hit rate target | Provider prompt only (GitHub-managed) | None disclosed | Limited | None disclosed | None |
| **Per-role / per-tool model routing** | **Yes** — operator-configurable (plan → cheap model, implementer → premium) | No (one Copilot model) | No (one Devin stack) | No | No | No |
| **Cost transparency to the user** | **Yes** — live `$/goal` counter + per-role cost breakdown in UI | Hidden in seat price | Hidden in tier price | Hidden in seat price | Hidden | N/A |
| **Deploy model** | Self-host (Docker / k8s) | SaaS (GitHub) | SaaS only | SaaS only | SaaS / self-host | Local IDE / CLI |
| **Openness** | Open source from day 1 | Closed | Closed | Closed | Open source | Open source |

### 5.1 The honest delta — what Cosign does and does NOT differentiate on

Be precise about this because it changes how we pitch.

**Cosign does NOT differentiate on:**
- *Drafting a first version of code or a review.* Copilot Coding Agent, CodeRabbit, Devin, Sweep all draft. So does Cosign. **Not a differentiator.**
- *Having a human in the loop somewhere.* Copilot's user iterates via PR comments; CodeRabbit's user reads the bot's review before merging. They also have HITL. **Not a differentiator.**

**Cosign DOES differentiate on five concrete things:**

1. **An AI critic — not the user — drives the iteration loop.** Copilot's pattern is: bot pushes → user reads → user comments → bot pushes again → user reads again. Every round is a context switch for the user. Cosign's pattern is: implementer ↔ critic loop runs to convergence (numeric self-satisfaction threshold or max iterations) *inside the worker*; the user enters **once**, at the end, to cosign. **3 rounds = 3 user context switches in Copilot vs 1 in Cosign.**

2. **The artifact is posted under the user's name, not a bot's.** Copilot's PR is authored by `copilot-swe-agent[bot]`; CodeRabbit's review is posted by `coderabbit[bot]`. Cosign's PR and review are posted via the user's OAuth, so on GitHub they appear authored by the user. This matters for: OSS contribution credit, internal-rep at work, maintainers who filter out bot PRs, GitHub profile signal.

3. **The iteration is private.** Copilot's exploratory mess is committed to the public PR for everyone to see. Cosign's iteration happens inside the worker; the public PR shows one clean diff. This matters for code review hygiene and for not subjecting the contributor (whose issue you're fixing) to a stream of bot-noise.

4. **The user sees reasoning, not just output, at decision time.** Copilot shows you a PR; you verify the code. Cosign shows you a transcript of implementer drafts + critic pushback + how the diff evolved, plus the final diff. You're verifying *the reasoning that produced the output*, not just the output. Stronger basis for trust, and the basis for the "cosign" gesture being meaningful instead of a rubber stamp.

5. **3–6× cheaper per shipped PR — and you can see exactly why.** Competitors hide LLM cost inside seat pricing ($20–500/dev/month) because their margin depends on you not noticing. Cosign is open-source and shows you the receipts: a live `$/goal` counter, a per-role cost breakdown (plan $0.003 · critic $0.008 · implementer $0.06), and a cache hit-rate dashboard. The mechanics: **multi-layer caching** (provider prompt cache + 4 Redis caches) drives a >50% hit rate, and **per-role LLM routing** lets the operator point cheap work (planning, criticism) at cheap models (Groq Llama / GPT-4o-mini / Claude Haiku) while reserving premium models (Claude Sonnet) for the value-critical implementer pass. Result: <$0.10 per shipped PR — vs ~$0.45 if everything ran on Sonnet end-to-end.

### 5.2 One-line vs each main competitor

- **vs Copilot Coding Agent:** Copilot makes a bot ship a PR you helped iterate on. Cosign makes *you* ship a PR an AI critic iterated on for you — at ~⅙ the cost.
- **vs CodeRabbit:** CodeRabbit puts a bot on the PR alongside you, billed by seat. Cosign puts you on the PR with AI help nobody else sees, and shows you exactly what each goal cost.
- **vs Devin:** Devin is autonomous (and the PR shows it). Cosign is your draft, your call, your name on the PR — and you self-host with your own API keys, paying $0.05–0.10/PR instead of $20–500/month.

These differences are subtle in marketing but visceral in use — the demo carries them in 30 seconds (see [ROADMAP §Demo Script](./ROADMAP.md)).

---

## 6. Core Feature Set

### 6.1 Flow A — User-Initiated PR Review

**The user opens the Cosign UI, finds a PR they want to review, and clicks "Review with Cosign".** The bot does not auto-react. This is the core difference from CodeRabbit / Sweep / PR-Agent.

The PR can be on any of:
- A repo the user owns and has connected via the GitHub App (their PR or a contributor's PR).
- A public repo where the user has OAuth access (e.g., they're a regular contributor).
- Any public PR URL they paste directly.

```
1. User clicks [Review with Cosign] on a PR in the Cosign UI
   (or pastes a PR URL into the "Review any PR" input)
        │
        ▼
2. cosign-api creates a Goal of type=pr_review,
   records the initiating user_id + target PR
        │
        ▼
3. cosign-worker spawns reviewer agent in sandboxed container,
   reads the PR diff using the USER'S OAuth token (so private-repo
   access matches what the user themselves can see)
        │
        ▼
4. Reviewer agent reads diff + relevant context files,
   produces a structured review draft:
     { summary, risk_score, per_file_comments, ask_changes, praise }
        │
        ▼
5. SSE event 'gate.pending' fires; web UI shows the draft review
   in an inline editor with [Edit & Cosign] / [Regenerate w/ note] / [Cancel]
        │
        ▼
6. User edits any wording they disagree with, then clicks [Cosign]
        │
        ▼
7. cosign-api posts the review on the PR using the user's OAuth token
   — comment is authored by the USER, not by a bot account.
   audit_log records: actor=user, action=cosign_review, payload_hash=...
```

**Key behaviors:**
- The review on GitHub is **authored by the user**, not by a `cosign[bot]` identity. No external observer can tell AI helped draft it; that's intentional and is what differentiates from CodeRabbit-style bots.
- Cosign never auto-runs on webhook events. Webhooks can optionally surface "new PR on your repo — want to review it?" notifications in the Cosign inbox, but the agent runs only when the user clicks.
- The user can request the agent to also draft *suggested code changes* (a follow-up "Implement these suggestions?" flow), but that's a separate user-initiated step, not automatic.

### 6.2 Flow B — User-Initiated Issue → PR

**The user opens the Cosign UI, picks an issue (theirs or anyone's public), and clicks "Resolve with Cosign".** They can optionally add context ("the fix should also update tests under tests/foo/"). The bot does not auto-react to `issues.assigned` events.

The issue can be on any of:
- A repo the user owns/has the App on → PR opens directly on that repo.
- A public repo they don't own → Cosign forks the repo to the user's account, then opens the PR upstream from the fork (fork-mode, §6.3).

```
1. User clicks [Resolve with Cosign] on an issue in the Cosign UI
   (or pastes an issue URL + optional steering note)
        │
        ▼
2. cosign-api creates Goal of type=issue_implement,
   detects whether target repo is in user's installations
   → if yes: fork_mode=false   if no: fork_mode=true
        │
        ▼
3. cosign-worker spawns implementer agent in sandboxed container
   - fork_mode=false: clones origin repo
   - fork_mode=true: forks via user's OAuth → clones the user's fork
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
   + final diff; web UI shows TranscriptViewer + cosign button
        │
        ▼
6. User cosigns ──► cosign-worker pushes branch via user's OAuth +
                    opens PR (own repo direct OR upstream from fork)
                    — PR is authored by the USER, not by a bot
   User revises ──► implementer re-runs with user's feedback prepended
   User rejects ──► goal marked cancelled
```

**Key behaviors:**
- Loop exit threshold and max-iters are configurable per-goal (defaults: 0.85, 5).
- The iteration transcript records: per-round prompt, per-round diff, per-round self-satisfaction score, per-round critic feedback. Stored in `critic_iterations` table, surfaced as collapsible per-round blocks in the UI.
- The user can manually inject feedback mid-loop via a "Steer" action in the UI that pauses the loop, accepts text, and resumes with that input prepended to the next implementer prompt.
- The opened PR is **authored by the user** (via their OAuth token) — no `cosign[bot]` identity on the PR.

### 6.3 Fork-mode (when the user doesn't own the repo)

For any flow targeting a repo not in the user's installations, Cosign automatically:
1. Uses the user's OAuth token to fork the upstream repo into their GitHub account (idempotent — reuses existing fork if present).
2. Hard-resets the fork's default branch to upstream to avoid stale state.
3. Runs the agent flow against the fork.
4. After cosign: pushes the branch to the fork, opens the PR upstream from the fork using the user's OAuth.

No `cosign[bot]` account is ever named anywhere. The user is the contributor of record on the upstream PR.

### 6.4 Agent Roles

Three agent roles in v1 (kept deliberately small).

| Role | Responsibility | Default LLM |
|---|---|---|
| **Implementer** | Reads issue/PR, writes code, runs tests in sandbox, emits self-satisfaction score | Anthropic Claude Sonnet 4.6 |
| **Reviewer** | Reads diff, produces structured review draft (summary, risk score, per-file comments, asks, praise) | Anthropic Claude Sonnet 4.6 |
| **Critic** | Reads diff + issue, produces structured feedback (blocking issues, suggestions, score) | Groq Llama 3.3 70B (fast, cheap for iteration) |

Multi-provider routing with Redis-tracked health (primary → fallback chain) lives in the worker.

### 6.5 Tool Ecosystem

| Tool | Category | Used by | Notes |
|---|---|---|---|
| `github_ops` | Integration | All | Read repos/issues/PRs/files, post comments-as-user, create PRs-as-user, fork repos, push branches. Always uses the invoking user's OAuth token. |
| `code_exec` | Execution | Implementer | Run shell commands inside the sandbox container; 30s timeout per call. |
| `file_ops` | Execution | Implementer | Read/write/delete files inside the sandboxed repo workspace. |
| `test_runner` | Execution | Implementer, Critic | Detects + runs the repo's test command (pytest / jest / go test / cargo test / `Makefile test`), parses results, returns pass/fail + failing tests. Lets the critic check claims like "tests pass". |
| `lint` | Execution | Implementer, Critic | Runs the repo's linter / formatter (eslint, ruff, gofmt, prettier) and returns violations. Cheap way to catch low-quality output before a critic round. |
| `repo_map` | Research | All | Builds a compact map of the repo (directory tree + top-level symbols per file via tree-sitter). Gives agents grounding without sending the whole repo as context. |
| `review` | Composition | Reviewer | Composes the structured review draft from prior tool outputs (diff + repo_map + lint results). Forces the review into a fixed schema the UI can render and edit. |
| `diff_analysis` | Research | Reviewer, Critic | Semantic diff breakdown: per-hunk classification (refactor / behavior change / test / docs / config), and detects suspicious patterns (secrets, CI changes, mass deletions). Drives the dangerous-action gate. |
| `web_search` | Research | All | Brave / Serper API with Redis-cached results (1h TTL). For looking up library docs, error messages, etc. |

All tool calls go through a capability check before execution (per-agent allowlist).

### 6.6 Human-in-the-Loop Interrupts

| Trigger | Payload | User actions |
|---|---|---|
| Reviewer finishes (Flow A) | Review draft (inline-editable) | Edit & Cosign / Regenerate w/ note / Cancel |
| Critic-loop exits (Flow B) | Iteration transcript + final diff | Cosign & open PR / Revise w/ feedback / Cancel |
| Implementer's `diff_analysis` flags a dangerous pattern (e.g., deleting >50% of a file, modifying CI config, secrets in diff) | Snippet + reason | Allow / Block |
| User clicks [Steer] in the UI during a running loop | Current state + transcript so far | Pause + accept text + resume with input prepended |

### 6.7 Iteration Transcript (First-Class Entity)

The transcript is **the** artifact a human reviews to cosign. It is:

- **Persisted** in the `critic_iterations` table (one row per round).
- **Streamed live** to the web UI via SSE during the loop.
- **Viewable post-hoc** as a collapsible per-round block: prompt, diff, self-satisfaction score, critic feedback.
- **Attached to the cosign event payload** so the audit log records exactly what the human saw at cosign time.
- **Exportable as a single JSON file** for offline review or sharing.

This is the differentiator that makes cosigning a meaningful gesture instead of a rubber stamp.

### 6.8 Cost Optimization (caching + per-role LLM routing)

Cosign treats LLM cost as a first-class concern, not an afterthought. Two mechanisms work together:

**(a) Multi-layer caching.** Every LLM call and tool call passes through a cache stack before the network is hit:
1. **Anthropic / OpenAI provider prompt cache** — system prompt + tool definitions + repo context block are explicitly cache-marked (Anthropic `cache_control` / OpenAI auto-cache ≥1024 tokens). Cache reads = 0.1× base price (90% off).
2. **Redis LLM exact-hash cache** — full prompt → response cached at 24h TTL for identical re-runs.
3. **Redis tool output cache** — per-tool TTL (GitHub reads 5 min via ETag, file reads 10 min, web search 1 h).
4. **Redis plan cache** — planning DAG cached at 12 h TTL keyed on normalized goal description.
5. **Redis GitHub ETag cache** — sends `If-None-Match`; 304 responses cost zero rate-limit budget.

Combined target hit rate: **>50%**.

**(b) Per-role / per-tool LLM routing.** Operators configure WHICH model handles WHICH node/tool via a single config file (`config/llm-routing.yaml`). Different agents use different providers and different API keys:

| Node / Role | Default model | Why |
|---|---|---|
| `plan_node` | Claude Haiku 4.5 (or GPT-4o-mini, or Groq Llama 3.3 70B) | Task decomposition into a DAG is mostly structuring — small models excel cheaply |
| `critic` | Groq Llama 3.3 70B | Fast iteration; cost matters because it fires N times per goal |
| `implementer` | Claude Sonnet 4.6 | Value-critical; the actual code |
| `reviewer` | Claude Sonnet 4.6 | Value-critical; the user's voice depends on quality |
| `tools.repo_map` | Local tree-sitter (no LLM) | Deterministic — no model call needed |
| `tools.diff_analysis` | Claude Haiku 4.5 | Classification task — Haiku is plenty |
| `tools.lint` | No LLM (runs actual linter) | Free |
| `tools.test_runner` | No LLM (runs actual tests) | Free |

Each role can use its own API key (operators bring their own keys per provider). Cost per goal is broken down per-role in `/metrics` and the goal-detail UI:

```
Goal #4711 — $0.067 total
  plan        Haiku       $0.003   (1 call,   1.8k in /  240 out)
  implementer Sonnet 4.6  $0.052   (4 calls, 18k in / 3.1k out — 64% cached)
  critic      Llama 3.3   $0.008   (3 calls,  9k in /  650 out)
  reviewer    —           —        (Flow B, no reviewer)
  tools                   $0.004   (web_search × 2)
```

**Result:** running the same Flow B goal with everything on Sonnet (no routing, no caching) benchmarks at ~$0.45. With routing + caching, the same goal lands at ~$0.07. **~6× cheaper, same output quality** — because the model picking the right model handles each part of the work in proportion to how much intelligence it actually needs.

---

## 7. Out of Scope (v1)

Explicitly **not** part of the 2026-06-10 delivery:

- Blockchain / on-chain identity / on-chain proofs / reputation NFTs.
- Webhook-driven auto-trigger of agent runs. Webhooks may feed an *inbox* of open PRs/issues a user might want to act on, but the agent only ever runs when the user clicks in the UI. This is deliberate, not a deferred feature.
- GitHub slash commands (`/cosign review` etc.). Same reason as above — the UI is the entrypoint.
- A `cosign[bot]` GitHub identity that posts reviews/comments/PRs on its own. All side effects are attributed to the invoking user via OAuth.
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
| 14 | Trigger model: user-initiated UI vs webhook-driven bot | **Decided** | **User-initiated**. Cosign is a web app, not a bot. Webhooks are at most a passive feed for the inbox; agents run only when the user clicks. The bot approach has many existing competitors (CodeRabbit, Sweep, PR-Agent); the UI-initiated approach is the differentiator. |
| 15 | Output attribution: bot account vs user-on-behalf | **Decided** | **User-on-behalf via OAuth**. Reviews, comments, and PRs are authored by the invoking user, not by a `cosign[bot]` account. This preserves the human voice and matches Scenarios 1–3 in §2.3. |
| 16 | GitHub App webhooks: subscribe and ignore, or skip subscribing | **Open** | Lean toward subscribing for the inbox feed (so the user sees "new PR on your repo" without polling), but with no auto-agent-run. Decide on Day 2. |
| 17 | Slash commands (`/cosign review`, `/cosign work`) as a secondary entrypoint | **Open** | Tentatively cut from v1 — UI is the entrypoint. Could re-add as a Day-9 stretch if users ask for it. |

---

*This document is the source of truth for Cosign's product scope. Implementation detail lives in [ARCHITECTURE.md](./ARCHITECTURE.md); the build schedule lives in [ROADMAP.md](./ROADMAP.md).*
