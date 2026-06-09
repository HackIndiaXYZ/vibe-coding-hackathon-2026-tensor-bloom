// Package apitypes defines the wire contract between cosign-api and cosign-web.
// The standard envelope wraps every REST response (ARCHITECTURE §8). TypeScript
// mirrors live in libs/ts-types/index.ts — keep them field-for-field in sync.
package apitypes

import "time"

// Envelope is the standard response wrapper: { data, meta, error }.
type Envelope struct {
	Data  any        `json:"data"`
	Meta  Meta       `json:"meta"`
	Error *APIError  `json:"error"`
}

type Meta struct {
	RequestID string `json:"request_id"`
	Timestamp string `json:"timestamp"`
}

type APIError struct {
	Code    string         `json:"code"`
	Message string         `json:"message"`
	Details map[string]any `json:"details,omitempty"`
}

// ── Auth ──────────────────────────────────────────────────────────────────────
type User struct {
	UUID        string  `json:"uuid"`
	GithubID    int64   `json:"github_id"`
	GithubLogin string  `json:"github_login"`
	AvatarURL   string  `json:"avatar_url"`
}

// ── Goals ─────────────────────────────────────────────────────────────────────
type GoalType string

const (
	GoalPRReview       GoalType = "pr_review"
	GoalIssueImplement GoalType = "issue_implement"
	GoalManual         GoalType = "manual"
)

type CreateGoalRequest struct {
	Type     GoalType `json:"type"`
	PRURL    string   `json:"pr_url,omitempty"`
	IssueURL string   `json:"issue_url,omitempty"`
	Steer    string   `json:"steer,omitempty"`
}

type GoalSummary struct {
	UUID        string     `json:"uuid"`
	Type        GoalType   `json:"type"`
	Title       string     `json:"title"`
	Status      string     `json:"status"`
	RepoFull    string     `json:"repo_full_name"`
	PRNumber    *int32     `json:"github_pr_number,omitempty"`
	IssueNumber *int32     `json:"github_issue_number,omitempty"`
	ForkMode    bool       `json:"fork_mode"`
	CreatedAt   time.Time  `json:"created_at"`
	CompletedAt *time.Time `json:"completed_at,omitempty"`
}

type GoalDetail struct {
	GoalSummary
	Description   string             `json:"description"`
	Interrupts    []Interrupt        `json:"interrupts"`
	Transcript    []CriticIteration  `json:"transcript"`
	CostBreakdown []CostRow          `json:"cost_breakdown"`
	OutputURL     string             `json:"output_url,omitempty"` // upstream PR/review URL
}

type Interrupt struct {
	UUID       string         `json:"uuid"`
	Type       string         `json:"type"` // pr_review_gate | critic_loop_gate | dangerous_code | steer
	Payload    map[string]any `json:"payload"`
	Decision   string         `json:"decision,omitempty"`
	ResolvedAt *time.Time     `json:"resolved_at,omitempty"`
}

type CriticIteration struct {
	Round            int32          `json:"round_number"`
	ImplementerDiff  string         `json:"implementer_diff"`
	SelfSatisfaction *float64       `json:"self_satisfaction,omitempty"`
	CriticFeedback   map[string]any `json:"critic_feedback,omitempty"`
}

type CostRow struct {
	Role         string  `json:"agent_role"`
	CallCount    int64   `json:"call_count"`
	TokensIn     int64   `json:"tokens_in"`
	TokensOut    int64   `json:"tokens_out"`
	CachedTokens int64   `json:"cached_tokens"`
	CostUSD      float64 `json:"cost_usd"`
}

// ── Resume (cosign / revise / reject) ─────────────────────────────────────────
type ResumeRequest struct {
	Decision     string         `json:"decision"` // approve | revise | reject
	Feedback     string         `json:"feedback,omitempty"`
	EditedReview *ReviewDraft   `json:"edited_review,omitempty"`
}

// ReviewDraft is the structured Flow A artifact the user edits + cosigns.
type ReviewDraft struct {
	Summary         string           `json:"summary"`
	RiskScore       float64          `json:"risk_score"`
	PerFileComments []PerFileComment `json:"per_file_comments"`
	AskChanges      []string         `json:"ask_changes"`
	Praise          []string         `json:"praise"`
}

type PerFileComment struct {
	Path    string `json:"path"`
	Line    int32  `json:"line,omitempty"`
	Comment string `json:"comment"`
}
