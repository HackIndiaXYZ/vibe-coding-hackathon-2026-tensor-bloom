-- ── Users ─────────────────────────────────────────────────────────────────────
-- name: UpsertUser :one
INSERT INTO users (github_id, github_login, github_oauth_token_encrypted, last_login_at)
VALUES ($1, $2, $3, NOW())
ON CONFLICT (github_id) DO UPDATE
  SET github_login = EXCLUDED.github_login,
      github_oauth_token_encrypted = EXCLUDED.github_oauth_token_encrypted,
      last_login_at = NOW()
RETURNING *;

-- name: GetUserByID :one
SELECT * FROM users WHERE id = $1;

-- name: GetUserByUUID :one
SELECT * FROM users WHERE uuid = $1;

-- name: GetUserByGithubID :one
SELECT * FROM users WHERE github_id = $1;

-- name: GetUserOAuthToken :one
SELECT github_login, github_oauth_token_encrypted
FROM users WHERE id = $1;

-- ── Repositories ──────────────────────────────────────────────────────────────
-- name: UpsertRepository :one
INSERT INTO repositories (github_repo_id, full_name, installation_id, default_branch)
VALUES ($1, $2, $3, $4)
ON CONFLICT (github_repo_id) DO UPDATE
  SET full_name = EXCLUDED.full_name,
      installation_id = EXCLUDED.installation_id,
      default_branch = EXCLUDED.default_branch
RETURNING *;

-- name: GetRepositoryByFullName :one
SELECT * FROM repositories WHERE full_name = $1;

-- ── Goals ─────────────────────────────────────────────────────────────────────
-- name: CreateGoal :one
INSERT INTO goals (
    user_id, repo_full_name, type, title, description,
    github_pr_number, github_issue_number, fork_mode, status
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'pending')
RETURNING *;

-- name: GetGoalByUUID :one
SELECT * FROM goals WHERE uuid = $1;

-- name: ListGoalsByUser :many
SELECT * FROM goals
WHERE user_id = $1
  AND (sqlc.narg('status')::text IS NULL OR status = sqlc.narg('status'))
ORDER BY created_at DESC
LIMIT $2 OFFSET $3;

-- name: UpdateGoalStatus :exec
UPDATE goals
SET status = $2,
    updated_at = NOW(),
    completed_at = CASE WHEN $2 IN ('done','failed','cancelled') THEN NOW() ELSE completed_at END
WHERE uuid = $1;

-- ── Tasks (read for goal detail) ──────────────────────────────────────────────
-- name: ListTasksByGoal :many
SELECT * FROM tasks WHERE goal_id = $1 ORDER BY id;

-- ── Critic iterations (Flow B transcript) ─────────────────────────────────────
-- name: ListCriticIterationsByGoal :many
SELECT * FROM critic_iterations
WHERE goal_id = $1
ORDER BY round_number;

-- ── Cost breakdown (per-role aggregation for a goal) ──────────────────────────
-- name: GoalCostBreakdown :many
SELECT
    t.agent_role,
    COUNT(*) FILTER (WHERE m.role = 'assistant')        AS call_count,
    COALESCE(SUM(m.tokens_in), 0)::bigint               AS tokens_in,
    COALESCE(SUM(m.tokens_out), 0)::bigint              AS tokens_out,
    COALESCE(SUM(m.cached_tokens), 0)::bigint           AS cached_tokens,
    COALESCE(ROUND(SUM(m.cost_usd), 6), 0)::float8      AS cost_usd
FROM messages m
JOIN tasks t ON m.task_id = t.id
WHERE t.goal_id = $1
GROUP BY t.agent_role
ORDER BY cost_usd DESC;

-- ── Interrupts (HITL gates) ───────────────────────────────────────────────────
-- name: CreateInterrupt :one
INSERT INTO interrupts (goal_id, type, payload_json)
VALUES ($1, $2, $3)
RETURNING *;

-- name: GetPendingInterrupt :one
SELECT * FROM interrupts
WHERE goal_id = $1 AND resolved_at IS NULL
ORDER BY created_at DESC
LIMIT 1;

-- name: ListInterruptsByGoal :many
SELECT * FROM interrupts WHERE goal_id = $1 ORDER BY created_at;

-- name: ResolveInterrupt :exec
UPDATE interrupts
SET decision = $2, feedback = $3, actor_user_id = $4, resolved_at = NOW()
WHERE id = $1;

-- ── Agents (capability check) ─────────────────────────────────────────────────
-- name: GetAgentByID :one
SELECT * FROM agents WHERE id = $1;

-- ── Audit log ─────────────────────────────────────────────────────────────────
-- name: InsertAuditLog :one
INSERT INTO audit_log (actor_type, actor_id, event_type, goal_id, payload_json, payload_hash)
VALUES ($1, $2, $3, $4, $5, $6)
RETURNING *;
