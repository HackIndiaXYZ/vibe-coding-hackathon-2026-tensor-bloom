-- Cosign — initial schema (MVP subset of ARCHITECTURE §4)
-- Tables actually touched by Flow A (pr_review) and Flow B (issue_implement).
-- Deferred for MVP: reputation, badges, inbox_items (left out; add in a later migration).

CREATE EXTENSION IF NOT EXISTS vector;        -- pgvector installed, unused in v1
CREATE EXTENSION IF NOT EXISTS pgcrypto;      -- gen_random_uuid()

-- ── Users + GitHub App installations ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id                            BIGSERIAL PRIMARY KEY,
    uuid                          UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    github_id                     BIGINT UNIQUE NOT NULL,
    github_login                  TEXT NOT NULL,
    github_oauth_token_encrypted  BYTEA,                 -- AES-GCM at rest
    created_at                    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at                 TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS installations (
    id                      BIGSERIAL PRIMARY KEY,
    github_installation_id  BIGINT UNIQUE NOT NULL,
    account_login           TEXT NOT NULL,
    account_type            TEXT NOT NULL,               -- 'User' | 'Organization'
    installed_by_user_id    BIGINT REFERENCES users(id),
    suspended_at            TIMESTAMPTZ,
    installed_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS repositories (
    id               BIGSERIAL PRIMARY KEY,
    github_repo_id   BIGINT UNIQUE NOT NULL,
    full_name        TEXT NOT NULL,                      -- "octocat/hello-world"
    installation_id  BIGINT REFERENCES installations(id),  -- NULL = fork-mode only
    default_branch   TEXT NOT NULL DEFAULT 'main',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_repos_install ON repositories(installation_id);

-- ── Agents (minimal — capability checks reference this) ───────────────────────
CREATE TABLE IF NOT EXISTS agents (
    id               BIGSERIAL PRIMARY KEY,
    uuid             UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    role             TEXT NOT NULL,                      -- 'implementer' | 'reviewer' | 'critic'
    display_name     TEXT NOT NULL,
    capabilities     JSONB NOT NULL,                     -- {tools:[...], repos:[...], trust_level:int}
    capability_hash  TEXT NOT NULL,                      -- SHA-256 of capabilities JSON
    active           BOOLEAN DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Goals + Tasks ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS goals (
    id                   BIGSERIAL PRIMARY KEY,
    uuid                 UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    user_id              BIGINT NOT NULL REFERENCES users(id),
    repository_id        BIGINT REFERENCES repositories(id),
    type                 TEXT NOT NULL,                  -- 'pr_review' | 'issue_implement' | 'manual'
    title                TEXT NOT NULL,
    description          TEXT,
    status               TEXT NOT NULL DEFAULT 'pending',
                         -- pending | planning | executing | awaiting_human | done | failed | cancelled
    github_pr_number     INTEGER,
    github_issue_number  INTEGER,
    fork_mode            BOOLEAN NOT NULL DEFAULT FALSE,
    output_json          JSONB,
    error                TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at         TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_goals_user_status ON goals(user_id, status);
CREATE INDEX IF NOT EXISTS idx_goals_repo        ON goals(repository_id);
CREATE INDEX IF NOT EXISTS idx_goals_created     ON goals(created_at DESC);

CREATE TABLE IF NOT EXISTS tasks (
    id             BIGSERIAL PRIMARY KEY,
    uuid           UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    goal_id        BIGINT NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    agent_id       BIGINT REFERENCES agents(id),
    agent_role     TEXT NOT NULL,
    tool_name      TEXT,
    args_json      JSONB,
    args_hash      TEXT,                                 -- SHA-256(args_json) for idempotency
    status         TEXT NOT NULL DEFAULT 'pending',
    result_json    JSONB,
    result_hash    TEXT,
    error          TEXT,
    attempt_count  INTEGER DEFAULT 0,
    started_at     TIMESTAMPTZ,
    completed_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_tasks_goal ON tasks(goal_id);

CREATE TABLE IF NOT EXISTS task_dependencies (
    task_id        BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    depends_on_id  BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    PRIMARY KEY (task_id, depends_on_id)
);

-- ── Critic iterations (Flow B transcript) ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS critic_iterations (
    id                  BIGSERIAL PRIMARY KEY,
    goal_id             BIGINT NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    round_number        INTEGER NOT NULL,               -- 0, 1, 2, ...
    implementer_prompt  JSONB NOT NULL,
    implementer_diff    TEXT,
    self_satisfaction   NUMERIC(3,2),                   -- 0.00 to 1.00
    critic_prompt       JSONB,                          -- NULL when loop exited by score
    critic_feedback     JSONB,                          -- {blocking_issues, suggestions, score}
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    UNIQUE (goal_id, round_number)
);

CREATE INDEX IF NOT EXISTS idx_critic_iter_goal ON critic_iterations(goal_id, round_number);

-- ── LLM messages (per-task history + cost source data) ────────────────────────
CREATE TABLE IF NOT EXISTS messages (
    id             BIGSERIAL PRIMARY KEY,
    task_id        BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    role           TEXT NOT NULL,                        -- system | user | assistant | tool
    content        TEXT NOT NULL,
    tool_name      TEXT,
    tool_args      JSONB,
    tokens_in      INTEGER,
    tokens_out     INTEGER,
    cached_tokens  INTEGER,                              -- provider cache_read / cached
    cost_usd       NUMERIC(10,6),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_task ON messages(task_id);

-- ── Interrupts (HITL gates) ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS interrupts (
    id             BIGSERIAL PRIMARY KEY,
    uuid           UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    goal_id        BIGINT NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    type           TEXT NOT NULL,                        -- pr_review_gate | critic_loop_gate | dangerous_code | steer
    payload_json   JSONB NOT NULL,
    decision       TEXT,                                 -- approve | revise | reject | NULL while pending
    feedback       TEXT,
    actor_user_id  BIGINT REFERENCES users(id),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_interrupts_pending ON interrupts(goal_id) WHERE resolved_at IS NULL;

-- ── Audit log ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
    id            BIGSERIAL PRIMARY KEY,
    actor_type    TEXT NOT NULL,                         -- user | agent | system
    actor_id      BIGINT,
    event_type    TEXT NOT NULL,                         -- goal_created | tool_call | cosign | goal_completed | ...
    goal_id       BIGINT REFERENCES goals(id),
    payload_json  JSONB,
    payload_hash  TEXT,                                  -- SHA-256 of payload
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_goal       ON audit_log(goal_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_actor      ON audit_log(actor_type, actor_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_log(event_type, created_at DESC);
