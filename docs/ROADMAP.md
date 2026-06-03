# Cosign — 8-Day Roadmap

**Hackathon delivery date:** 2026-06-10 (Wed)
**Start date:** 2026-06-02 (Tue) — Day 1
**Companion docs:** [PRD.md](./PRD.md) · [ARCHITECTURE.md](./ARCHITECTURE.md)

---

## At a Glance

| Day | Date | AM theme · PM theme | Cumulative demo count |
|---|---|---|---|
| 1 | Tue Jun 02 | docs · scaffolding | 0 |
| 2 | Wed Jun 03 | GitHub App · OAuth + webhook | 1 (auth + webhook) |
| 3 | Thu Jun 04 | SandboxDriver + DockerDriver · implementer agent v0 | 2 (+sandboxed agent) |
| 4 | Fri Jun 05 | reviewer agent · HITL gate + implementer follow-through | 3 (+Flow A end-to-end) |
| 5 | Sat Jun 06 | critic agent · critic-loop subgraph + transcript persistence | 4 (+Flow B end-to-end) |
| 6 | Sun Jun 07 | OAuth user-token + fork creation · fork-to-upstream PR flow | 5 (+fork-mode) |
| 7 | Mon Jun 08 | L2 prompt cache + Redis caches · /metrics + audit log + comparison page | 6 (+caching visible) |
| 8 | Tue Jun 09 | UI polish (event feed, gate modal, transcript viewer, audit viewer) · deploy + record demo | 6 polished + video |
| — | Wed Jun 10 | bug-fix buffer (AM) · submit (PM) | — |

---

## Day 1 — Tue Jun 02 — Docs + Scaffolding

**AM theme:** Documentation
**PM theme:** Repo scaffolding

### AM — Documentation
- [x] Write `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`
- [ ] Update top-level `README.md` to link to the three docs

### PM — Scaffolding
- [ ] Create monorepo layout:
  ```
  cosign/
  ├── services/
  │   ├── cosign-api/        (Go workspace, module github.com/tensor-bloom/cosign-api)
  │   ├── cosign-worker/     (uv project, pyproject.toml)
  │   └── cosign-web/        (Next.js 15 App Router via create-next-app)
  ├── libs/
  │   ├── proto/             (.proto files + buf.yaml + generated code)
  │   └── ts-types/          (TS types generated from Go apitypes)
  ├── infra/
  │   ├── docker-compose.yml
  │   ├── Caddyfile
  │   ├── sandbox.Dockerfile
  │   └── postgres/init.sql
  ├── scripts/
  │   ├── setup-dev.sh
  │   └── reset-db.sh
  └── docs/                  (already exists)
  ```
- [ ] `infra/docker-compose.yml`: Postgres 16 (pgvector) + Redis 7. Both with healthchecks.
- [ ] cosign-api: `go.mod`, chi router skeleton, `/health` endpoint, env-var loading via `envconfig`.
- [ ] cosign-worker: `pyproject.toml`, FastAPI skeleton, `/health` endpoint, asyncpg pool wiring.
- [ ] cosign-web: Next.js scaffold, Tailwind installed, single `/` page that fetches `/api/health` via a typed client stub.
- [ ] `scripts/setup-dev.sh`: checks deps (docker, go, uv, node), starts compose, runs migrations.

**Exit criterion:** `./scripts/setup-dev.sh` runs to completion. `curl localhost:8080/health` returns 200. `curl localhost:8000/health` (worker) returns 200. `open localhost:3000` shows a Next.js page that says "Cosign — healthy".

**Risks:**
- *Risk:* uv install slow on first run. *Mitigation:* prefetch wheels in setup-dev.sh.
- *Risk:* pgvector image pull slow on hackathon wifi. *Mitigation:* warm the image overnight Day 0.

**Parking lot:** Caddy config (Day 8), Dockerfile multi-stage builds (Day 8), CI pipelines (post-hackathon).

---

## Day 2 — Wed Jun 03 — GitHub App + OAuth + Webhooks

**AM theme:** Register the GitHub App and wire OAuth
**PM theme:** Webhook receiver + installation flow

### AM — GitHub App registration + OAuth login
- [ ] Register a new GitHub App at github.com/settings/apps/new
  - Name: `cosign-dev` (separate prod app later)
  - Webhook URL: ngrok tunnel to local cosign-api (`POST /webhooks/github`)
  - Permissions per ARCHITECTURE §7.1
  - Events: `pull_request`, `issues`, `issue_comment`, `installation`
- [ ] Download App private key (`.pem`), store in `.env` as `GITHUB_APP_PRIVATE_KEY_PATH`
- [ ] `cosign-api/internal/gateway/handlers/auth.go`:
  - `GET /auth/github/login` → redirect to GitHub OAuth (scopes: `read:user`, `public_repo`)
  - `GET /auth/github/callback` → exchange code, upsert into `users`, issue JWT cookie
- [ ] `cosign-api/internal/identity`: users table CRUD, JWT signing/verification
- [ ] cosign-web: login button → OAuth flow → land on `/` showing user's GitHub avatar + login

### PM — Webhook receiver (passive inbox feed only) + installation flow
- [ ] `GET /auth/github/install` → redirect to GitHub App install URL
- [ ] `cosign-api/internal/gateway/webhook/`:
  - HMAC-SHA256 verify against `GITHUB_WEBHOOK_SECRET`
  - Event dispatch: `installation.created` → upsert into `installations`; `installation.deleted` → soft-delete
  - `pull_request.opened` / `issues.opened` → INSERT into `inbox_items` (just feeds the user's inbox, **does not** trigger agents)
- [ ] Test on a throwaway test repo: install App, observe webhook lands and an inbox item appears.
- [ ] Run sqlc to generate query code for users/installations/repositories/inbox_items.

**Exit criterion:**
1. User clicks "Sign in with GitHub" on cosign-web → lands back signed in.
2. User clicks "Install Cosign on a repo" → completes install on a test repo → `installations` table has the row.
3. Open a PR on the test repo → cosign-api logs show `pull_request.opened` webhook HMAC-verified → inbox_items has a row → no agent runs (deliberate; agents only run when user clicks).

**Risks:**
- *Risk:* GitHub App webhook URL must be HTTPS — local dev needs a tunnel. *Mitigation:* use `cloudflared tunnel` or `ngrok http 8080`; document in setup-dev.sh.
- *Risk:* OAuth scope decisions block fork-mode later. *Mitigation:* request `public_repo` from the start so fork-mode (Day 6) doesn't need a re-consent flow.

**Parking lot:** Inbox UI polish (Day 8).

---

## Day 3 — Thu Jun 04 — Sandbox + First Agent

**AM theme:** SandboxDriver interface + DockerDriver
**PM theme:** Implementer agent v0 (single-shot, no critic loop)

### AM — Sandbox
- [ ] `cosign-worker/sandbox/driver.py`: `SandboxDriver` Protocol per ARCHITECTURE §6.1
- [ ] `cosign-worker/sandbox/docker_driver.py`: implementation using `aiodocker`
  - Build `cosign/sandbox:latest` image from `infra/sandbox.Dockerfile` (git, node, python, bash, curl)
  - Resource limits per ARCHITECTURE §6.2
  - Network: create `cosign_sandbox_net` Docker network; egress restricted
  - `commit_and_push` uses GIT_ASKPASS helper script for token auth
- [ ] Unit tests: start container, exec a command, read/write a file, stop. Confirm container is gone.

### PM — Implementer agent v0
- [ ] `cosign-worker/orchestration/state.py`: AgentState TypedDict (subset for Day 3 — full version on Day 5)
- [ ] `cosign-worker/orchestration/graph.py`: minimal LangGraph with `plan_node` → `implementer_node` → `finalize_node`
- [ ] `cosign-worker/orchestration/nodes/implementer.py`:
  - Acquire sandbox handle
  - Clone repo, checkout branch
  - LLM call (Anthropic Sonnet 4.6) to produce an edit
  - Apply edit via `write_file`
  - Run tests via `exec` (if test command provided)
  - Return result
- [ ] `cosign-worker/llm/router.py`: LiteLLM wrapper, just Anthropic for now (multi-provider on Day 7)
- [ ] gRPC: stub `SubmitGoal` on worker; cosign-api gRPC client stub
- [ ] cosign-api: `POST /goals` handler (manual goal submission, no GitHub yet) → INSERT goals → gRPC SubmitGoal → poll for done

**Exit criterion:** `curl -X POST localhost:8080/goals -d '{"type":"manual","repo_url":"...","description":"add a line to README"}'` → after ~30s, the goal completes; the line is committed and pushed to a branch in the target repo; `GET /goals/{uuid}` shows the result.

**Risks:**
- *Risk:* DockerDriver flakiness on first run. *Mitigation:* Day 3 AM is fully timeboxed; cut the network firewall down to "allow github.com only" if iptables sidecar takes too long; full firewall hardens on Day 7.
- *Risk:* Anthropic key rate limits with multiple test runs. *Mitigation:* keep dev iteration on a cheap mock LLM for fast inner loops; only hit Anthropic for end-to-end runs.

**Parking lot:** Capability checks (Day 4), Redis tool cache (Day 7).

---

## Day 4 — Fri Jun 05 — Flow A End-to-End

**AM theme:** Reviewer agent
**PM theme:** HITL gate + implementer follow-through

### AM — Reviewer agent
- [ ] `cosign-worker/orchestration/nodes/reviewer.py`:
  - Read PR diff via github_ops
  - Read up to 10 most-relevant files via file_ops in sandbox
  - LLM call (Anthropic Sonnet) → structured review artifact:
    ```json
    { "summary": "...", "risk_score": 0.3, "per_file_comments": [...], "suggested_changes": [...] }
    ```
- [ ] `cosign-worker/tools/github.py`: `get_pr_diff`, `post_pr_comment`, `update_check_run`
- [ ] Capability check wired: agents have `capabilities.tools = ["github_ops", "file_ops", "code_exec"]`

### PM — User-initiated trigger + HITL gate + review-post-as-user
- [ ] `cosign-worker/orchestration/interrupts.py`: gate helpers
- [ ] `cosign-worker/orchestration/nodes/finalize.py`: writes interrupt + uses `graph.interrupt()` for HITL pause
- [ ] cosign-api: SSE multiplexer subscribed to `stream:goal:{goal_id}` Redis Stream
- [ ] cosign-api: `POST /goals/{uuid}/resume` writes decision + edited_review to `interrupts`, calls gRPC `ResumeFromInterrupt`
- [ ] cosign-web: `/repos/[owner]/[repo]/pulls/[n]` page with `[Review with Cosign]` button + live event feed (basic, polish on Day 8) + `<ReviewEditor>` modal that renders on `gate.pending` (inline-editable review draft)
- [ ] cosign-web: also wire `/review?pr_url=...` for the "Review any PR" flow (paste any PR URL)
- [ ] Wire Flow A trigger: button click → `POST /goals { type:"pr_review", pr_url }` → kick off reviewer
- [ ] On cosign: cosign-api POSTs the (possibly user-edited) review on the PR via the **user's OAuth token** so the review is attributed to the user, not a bot

**Exit criterion (Flow A end-to-end):**
1. User signs in, opens a PR in the Cosign UI (or pastes a PR URL).
2. User clicks [Review with Cosign].
3. Reviewer agent runs in sandbox → produces review draft → `gate.pending` event fires.
4. cosign-web shows the ReviewEditor modal with the draft inline.
5. User tweaks two lines → clicks [Cosign].
6. Review posts on the PR on GitHub — authored by the user (their avatar, their handle), **not** a bot account.

**Risks:**
- *Risk:* Implementer's test-run inside sandbox is slow on a real repo. *Mitigation:* time-box exec at 60s; surface test failure to user via a follow-up interrupt rather than blocking.
- *Risk:* Reviewer hallucinates files that don't exist. *Mitigation:* file_ops returns clear "not found" errors; system prompt explicitly forbids inventing paths.
- *Risk:* OAuth scope insufficient to post a review on a public repo. *Mitigation:* `public_repo` scope (already requested Day 2) covers `POST /repos/{owner}/{repo}/pulls/{n}/reviews`; verify on Day 2 EOD with a manual API call.

**Parking lot:** Implementer follow-through (auto-applying suggestions and pushing a commit) — moved to a Day-9 stretch since Flow A's main differentiator is the **user-authored review**, not the auto-commit. If the user wants to apply suggestions, they can click [Resolve with Cosign] on a follow-up issue/PR.

---

## Day 5 — Sat Jun 06 — Flow B Critic Loop

**AM theme:** Critic agent
**PM theme:** Critic-loop subgraph + transcript persistence + Flow B trigger

### AM — Critic agent
- [ ] `cosign-worker/orchestration/nodes/critic.py`:
  - Read state.diff + issue body + repo context
  - LLM call (Groq Llama 3.3 70B for speed)
  - Structured output:
    ```json
    { "blocking_issues": [...], "suggestions": [...], "score": 0.4, "rationale": "..." }
    ```
- [ ] Extend implementer to emit `self_satisfaction` (float 0–1) every round, reading prior critic feedback if present
- [ ] Update AgentState to include `critic_iterations: list[dict]` and `current_round: int`

### PM — Critic-loop subgraph
- [ ] `cosign-worker/orchestration/nodes/critic_loop.py`: builds the subgraph per ARCHITECTURE §3.2 step 4
  - Loop control: `should_continue(state) -> Literal["implementer","exit"]`
- [ ] Per-round DB writes: each implementer turn and each critic turn writes/updates a row in `critic_iterations`
- [ ] SSE events: `iteration.implementer` (with round + self_satisfaction) and `iteration.critic` (with round + feedback)
- [ ] Wire Flow B trigger: cosign-web `/repos/[owner]/[repo]/issues/[n]` page with `[Resolve with Cosign]` button + optional steering note → `POST /goals { type:"issue_implement", issue_url, steer? }` → kick off critic_loop_subgraph
- [ ] Also wire `/resolve?issue_url=...` for paste-any-issue flow
- [ ] At loop exit: write the gate interrupt with payload containing the full transcript + final diff
- [ ] cosign-web: `<TranscriptViewer>` component (raw / collapsible blocks; polish Day 8) + integrate into CosignGate
- [ ] On cosign: push branch + open PR via the **user's OAuth token** (own repo direct or upstream-from-fork if Day 6 fork-mode is ready)

**Exit criterion (Flow B end-to-end):**
1. User opens an issue in the Cosign UI (or pastes an issue URL).
2. User clicks [Resolve with Cosign], optionally adds a steering note.
3. SSE feed shows implementer round 0 (with self_satisfaction score) → critic round 0 → implementer round 1 → ... until exit.
4. Gate appears with the transcript + final diff.
5. User cosigns → PR opens on GitHub authored by the user.

**Risks:**
- *Risk:* loop never converges (self_satisfaction stays low for buggy implementer). *Mitigation:* max_iters cap (default 5) hard-stops the loop; gate always surfaces eventually.
- *Risk:* critic and implementer disagree forever (loop oscillates). *Mitigation:* include prior iterations in implementer's prompt so it sees its own history; if score *decreases* across two rounds, force-exit with that observation surfaced.
- *Risk:* transcript gets large (token-wise) and the cosign payload bloats the SSE event. *Mitigation:* SSE event includes only `iteration_count` + summary; client fetches full transcript via `GET /goals/{id}/transcript` on gate open.

**Parking lot:** [Steer] button to inject mid-loop feedback in the UI (post-hackathon if not reached during PM).

---

## Day 6 — Sun Jun 07 — Fork-mode for Upstream Repos

**AM theme:** OAuth user-token usage + fork creation
**PM theme:** Fork-to-upstream PR flow + auto-detect

### AM — OAuth user-token + fork
- [ ] Verify OAuth scopes captured Day 2 include `public_repo` (re-consent if not)
- [ ] `cosign-worker/tools/github.py` add:
  - `fork_repo(upstream_owner, repo, user_token) -> fork_url`
  - `clone_fork(handle, fork_url, user_token)` — uses user's token, not App token
  - `push_to_fork(handle, branch, user_token)`
  - `open_upstream_pr(upstream_owner, repo, head_user_login, head_branch, title, body, user_token)`
- [ ] Identity service: decrypt user OAuth token on demand for worker (gRPC: `GetUserOAuthToken(user_id)` — requires worker auth)

### PM — Fork mode trigger + UI
- [ ] cosign-api `POST /goals`: if target repo not in `installations`, set `goal.fork_mode = true`
- [ ] cosign-worker: branch on `goal.fork_mode`:
  - True → fork-mode flow per ARCHITECTURE §7.2
  - False → standard App flow
- [ ] cosign-web: on goal creation, if user hasn't granted OAuth or token expired, surface "Connect GitHub for fork-mode" CTA
- [ ] Rate limit: 5 fork-mode goals per user per hour (Redis sliding window)

**Exit criterion (fork-mode end-to-end):**
1. User submits a goal targeting `popular-org/popular-repo` (Cosign App NOT installed).
2. Web UI surfaces: "This repo doesn't have Cosign installed. We'll fork and open a PR upstream from your account."
3. User confirms → if OAuth not granted yet, redirect to grant.
4. cosign-worker forks `popular-org/popular-repo` to `{user_login}/popular-repo`.
5. Implementer agent runs in sandbox against the fork.
6. Gate surfaces → user cosigns.
7. Worker pushes branch to fork → opens PR upstream from fork → PR is authored by the user.
8. Goal detail in UI links to the upstream PR.

**Risks:**
- *Risk:* User's OAuth token expired. *Mitigation:* detect 401 from GitHub, surface re-auth modal immediately.
- *Risk:* Existing fork has stale code. *Mitigation:* always do `git fetch upstream && git reset --hard upstream/{default_branch}` before edits.
- *Risk:* Hitting abuse triggers on popular repos. *Mitigation:* repo allowlist for the public demo deployment; aggressive per-user rate limit.

**Parking lot:** Fork-mode for private repos requiring OAuth `repo` scope (not `public_repo`) — post-hackathon.

---

## Day 7 — Mon Jun 08 — Cost Optimization (caching + per-role routing) + Observability

**AM theme:** Caching (5 layers) + per-role LLM routing config
**PM theme:** Cost dashboard in UI + `/metrics` + audit log writes + comparison page

### AM — Caching + Per-Role Routing (the cost-optimization story)
- [ ] `cosign-worker/llm/prompt_cache.py`: Anthropic `cache_control` wrapper per ARCHITECTURE §5.1; OpenAI auto-cache stable prefix audit
- [ ] Audit every system prompt to ensure static-first / dynamic-last ordering
- [ ] `cosign-worker/cache/llm_exact.py`: Redis wrapper per ARCHITECTURE §5.2
- [ ] `cosign-worker/cache/tool_output.py`: per-tool TTLs; `BaseTool.cacheable` opt-in
- [ ] `cosign-worker/cache/plan.py`: 12h TTL on planning calls
- [ ] `cosign-worker/tools/github.py`: ETag cache wired (send `If-None-Match`, handle 304)
- [ ] **`cosign-worker/llm/router.py`: per-role LLM router per ARCHITECTURE §5.7**
  - Load `config/llm-routing.yaml` at startup
  - `router.acall(role="plan_node" | "critic" | "implementer" | "reviewer", tool=..., messages=...)`
  - Per-role API keys via env-var resolution
  - Health-tracked fallback chains per role (Redis-backed)
- [ ] **Wire each LangGraph node + each tool through the router** (no direct `litellm.acompletion` calls anywhere outside `llm/router.py`)
- [ ] **Default routing config to ship:** plan_node → Claude Haiku · critic → Groq Llama 3.3 70B · implementer/reviewer → Claude Sonnet 4.6 · diff_analysis → Haiku · repo_map/lint/test_runner → `provider: none` (local-only)
- [ ] Cost tracking: every `messages` row records `tokens_in`, `tokens_out`, `cached_tokens`, `cost_usd` (use LiteLLM's `completion_cost` helper)

### PM — Cost dashboard + Observability + Audit + Comparison page
- [ ] **Per-goal cost breakdown SQL view** (ARCHITECTURE §5.8); exposed via `GET /goals/{uuid}` as `cost_breakdown`
- [ ] **cosign-web: goal-detail page shows cost-by-role bar at the top** (e.g., `plan $0.003 · critic $0.008 · implementer $0.052 · tools $0.004 = $0.067`)
- [ ] **cosign-web: `/cost` dashboard page** — running total $/goal across all goals; cache hit rate; cost-mix ratio (cheap models ÷ premium models)
- [ ] Wire Prometheus `/metrics` on cosign-api (chi-prometheus) and cosign-worker (prometheus-fastapi-instrumentator)
- [ ] Add cost metrics: `cosign_worker_goal_cost_usd_sum{role}`, `cosign_worker_cache_hits_total{cache}`, `cosign_worker_llm_tokens_total{provider,model,direction,cached}`
- [ ] Audit log writes: every gateway action, every tool call, every cosign, every goal status change
- [ ] cosign-web: `/audit` page with table + filters (goal, actor, event_type, date range) + JSONL export
- [ ] cosign-web: `/compare` page with the competitive table from PRD §5 (server-rendered, no live data)

**Exit criterion:**
1. Run a goal once → run an identical goal → second run shows ≥50% input-token reduction and **≥50% lower $/goal** in the UI cost bar.
2. Same Flow B goal run with single-Sonnet routing benchmarks at ~$0.45; with default routing benchmarks at <$0.10. Both numbers visible in the UI.
3. `/cost` dashboard renders the running totals.
4. `/audit` page renders the full event log for a recent goal.
5. `/compare` page renders the competitive table including the new cost rows.

**Risks:**
- *Risk:* Anthropic cache breakpoint placement wrong → no hits. *Mitigation:* explicit logging of `cache_read_input_tokens` from response; fail loud if hit rate is 0 after 3 runs.
- *Risk:* ETag cache returns stale data (GitHub edge cache disagrees with our cache). *Mitigation:* 5min TTL is short enough that drift is bounded; bypass on `X-Cache-Bypass`.
- *Risk:* Per-role routing config drift — config + code disagree on role names. *Mitigation:* unit test that every role string referenced in any node appears in `llm-routing.yaml`.
- *Risk:* Groq rate limits during demo. *Mitigation:* fallback chain (Groq → Haiku → OpenAI mini) declared in routing config; verify failover on a manual triggered 429.

**Parking lot:** Grafana dashboard (Cut Line #1 if behind), Jaeger tracing (post-hackathon).

---

## Day 8 — Tue Jun 09 — Polish + Deploy + Demo Video

**AM theme:** UI polish
**PM theme:** Deploy to demo VM + record demo

### AM — UI polish
- [ ] `<EventFeed>`: tidy event rendering (icons per event type, timestamps, expand/collapse)
- [ ] `<CosignGate>`: clean approve/revise/reject flow, feedback textarea for revise, keyboard shortcuts (a/r/x)
- [ ] `<TranscriptViewer>`: per-round collapsible blocks with syntax-highlighted diff, self-satisfaction score visualized as a bar
- [ ] `<DiffViewer>`: integrate `@git-diff-view/react` or similar for proper hunk rendering
- [ ] `<AuditLog>`: pagination, filter chips, export-as-JSONL button
- [ ] `/inbox` page: queue of pending cosign gates across all user's goals; click → goal detail with gate open
- [ ] Mobile-responsive smoke test (gates need to work on phone for the over-the-shoulder demo)
- [ ] Landing page polish on `/` (one screenshot, one tagline, two CTAs: Install App / Try fork-mode)

### PM — Deploy + record demo
- [ ] Provision demo VM (Hetzner CX22 or similar): provision, install docker, copy compose, bring up
- [ ] Caddy + auto-TLS for `cosign-demo.{tensor-bloom.dev?}` (or similar domain)
- [ ] Register a separate `cosign-prod` GitHub App with the demo VM as webhook URL
- [ ] Smoke test: do a full Flow A run, Flow B run, fork-mode run against demo VM
- [ ] Record the demo video (3–4 min, script in §Demo Script below); upload to YouTube unlisted
- [ ] Update top-level `README.md`: project description, install instructions, link to demo video, link to docs

**Exit criterion:**
1. Demo VM is up at HTTPS endpoint with valid cert.
2. End-to-end Flow A + Flow B + fork-mode all work against the live deployment.
3. Demo video recorded and uploaded.
4. README has working links to all three docs + demo video + deployment.

**Risks:**
- *Risk:* DNS / cert provisioning takes longer than expected. *Mitigation:* warm the domain Day 7 evening; have a fallback `*.nip.io` plan.
- *Risk:* A bug discovered while recording the demo. *Mitigation:* Day 9 AM is a buffer specifically for this. Record a backup demo with a known-good repo Day 8 night.

**Parking lot:** None — Day 9 is the buffer.

---

## Day 9 — Wed Jun 10 — Submission

**AM:** Bug-fix buffer. Anything discovered during the Day 8 demo recording gets fixed here.
**PM:** Submit to the hackathon. Confirm submission. Tweet/post the demo link.

---

## Demo Script (Day 8 Recording Target — 3 to 4 minutes)

Recorded as a single take if possible. Narration over screen capture.

**0:00–0:15 — Opening (15s)**
> "Cosign is a web app for developers. AI drafts your code reviews and your issue fixes. You always edit and cosign before anything ships — under your name, not a bot's. Watch."

**0:15–0:45 — Flow A: User-initiated PR review, posted as the user (30s)**
- Open the Cosign dashboard. Click on an open PR from the inbox (or paste any PR URL).
- Click [Review with Cosign]. Live event feed scrolls as the reviewer agent runs.
- ReviewEditor opens with a structured draft inline. Edit two lines.
- Click [Cosign]. Cut to GitHub: the review now appears on the PR — **authored by the user**, no bot account visible. Highlight that detail.

**0:45–2:15 — Flow B: Critic-loop with self-satisfaction (90s)**
- Open an issue tagged `good-first-issue` in the Cosign UI.
- Click [Resolve with Cosign], type a short steering note.
- Event feed shows round 0 implementer → score 0.62.
- Critic round 0 → feedback about missing edge cases.
- Round 1 implementer → score 0.78.
- Critic round 1 → feedback about test coverage.
- Round 2 implementer → score 0.91 → loop exits.
- Gate appears with full TranscriptViewer. Expand a round. Show how the diff evolved.
- Click [Cosign & open PR]. Cut to GitHub: PR opens, **authored by the user**.

**2:15–3:00 — Fork-mode for upstream OSS (45s)**
- Paste a URL to a popular upstream repo the user doesn't own (e.g., a one-line typo on a popular README).
- UI: "This repo isn't in your installations. We'll fork it to your account and open the PR upstream from your fork."
- OAuth prompt (if first time).
- Fork created. Implementer runs. Gate appears. Cosign.
- Cut to GitHub: PR opens upstream from the user's fork, authored by the user.

**3:00–3:30 — Cost story: caching + per-role routing (30s)**
- Open `/cost` dashboard. Show running totals across goals.
- Open the Flow B goal from 0:45. Cost bar at top: `plan $0.003 (Haiku) · critic $0.008 (Llama) · implementer $0.052 (Sonnet) · tools $0.004 = $0.067 total`.
- Toggle the dev-only "what if everything ran on Sonnet" button: cost jumps to $0.45 — **~6.5× more**.
- Voiceover: "Competitors charge $20–500/dev/month. Cosign is open-source, you bring your own keys, and you see exactly what each goal cost. Cheap models do the cheap work."

**3:30–end — Outro (≤30s)**
> "User-initiated. Cosigned by you. Posted as you. ~6× cheaper. Open source from day one. Repo and docs at github.com/.../cosign."

---

## Cut Lines (in priority order — drop in this order if behind)

| # | Cut | When triggered | Effort saved | Demo cost |
|---|---|---|---|---|
| 1 | Day 7 PM: drop `/compare` page from UI; keep table in README only | End of Day 7 if AM caching+routing ran long | ~2 hrs | Low |
| 2 | Day 8 AM: drop transcript viewer polish; show raw JSON expandable | End of Day 7 if Day 7 PM ran long | ~3 hrs | Medium (transcript is the differentiator UX) |
| 3 | Day 6: ship App-only on 10 Jun; defer fork-mode to Day 9 stretch | If Day 5 spilled over | ~6 hrs | High (kills Scenario 2 of the demo) |
| 4 | Day 5: critic-loop becomes single critic pass (no loop) | Last resort | ~4 hrs | Very High (kills the strongest innovation) |
| 5 | Day 7 PM: drop audit log; ship cache + cost metrics only | If Day 7 AM ran long | ~2 hrs | Medium |
| 6 | Day 7 AM: ship per-role routing with hardcoded defaults (no YAML config file) | If routing wiring blows up | ~2 hrs | Low (cost story still works; just less operator-friendly) |

**Do NOT cut:** the 5-layer cache stack and per-role routing entrypoint. These are core to the cost-savings selling point in PRD §1.2 point 6 and the demo's 3:00–3:30 segment. If Day 7 is fundamentally blocked, the right move is to descope the comparison/audit pages first.

**Cut order discipline:** never cut Day 4 (Flow A) or Day 3 (sandbox + agent). Those are existential. Cut order respects: kill polish before killing features; kill secondary innovations before killing core ones.

---

## Appendix: What We Cut and Why

Filled in as we go. Each row: which cut was triggered, on which day, what triggered it.

| Date | Cut # | Triggered by |
|---|---|---|
| _empty_ | | |

---

## Appendix: Daily Owner Assignments

To be filled in once the team is locked. Default placeholder: solo build.

| Day | Owner(s) |
|---|---|
| Day 1 | — |
| Day 2 | — |
| Day 3 | — |
| Day 4 | — |
| Day 5 | — |
| Day 6 | — |
| Day 7 | — |
| Day 8 | — |
| Day 9 | — |

---

*Scope rationale lives in [PRD.md](./PRD.md). Technical detail lives in [ARCHITECTURE.md](./ARCHITECTURE.md). This document is the single source of truth for delivery schedule — if it isn't on the roadmap, it isn't shipping on 10 Jun.*
