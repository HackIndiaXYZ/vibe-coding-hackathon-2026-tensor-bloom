package handlers

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"regexp"
	"strconv"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/google/go-github/v66/github"
	"github.com/google/uuid"
	"golang.org/x/oauth2"

	gwmw "github.com/tensor-bloom/cosign/services/cosign-api/internal/gateway/middleware"
	"github.com/tensor-bloom/cosign/services/cosign-api/internal/gateway/respond"
	"github.com/tensor-bloom/cosign/services/cosign-api/internal/identity"
	"github.com/tensor-bloom/cosign/services/cosign-api/internal/orchestration"
	"github.com/tensor-bloom/cosign/services/cosign-api/internal/store"
	"github.com/tensor-bloom/cosign/services/cosign-api/pkg/apitypes"
)

var (
	prRe    = regexp.MustCompile(`github\.com/([^/]+)/([^/]+)/pull/(\d+)`)
	issueRe = regexp.MustCompile(`github\.com/([^/]+)/([^/]+)/issues/(\d+)`)
)

type GoalsHandler struct {
	Q               *store.Queries
	Crypto          *identity.Crypto
	Worker          *orchestration.Client
	Log             *slog.Logger
	CapUSD          float64 // per-user demo budget on the shared key (0 = disabled)
	DefaultProvider string  // operator default provider when the user hasn't overridden
}

// budgetAllowed reports whether the user may start a goal under the demo budget.
// Users who fund the effective default provider with their OWN key are uncapped;
// otherwise their operator-funded spend must be under CapUSD.
func (h *GoalsHandler) budgetAllowed(ctx context.Context, userID int64) (bool, error) {
	if h.CapUSD <= 0 {
		return true, nil // cap disabled (dev)
	}
	// effective default provider: the user's _default override, else operator default
	provider := h.DefaultProvider
	if raw, err := h.Q.GetUserRouting(ctx, userID); err == nil && len(raw) > 0 {
		var routing map[string]apitypes.RouteChoice
		if json.Unmarshal(raw, &routing) == nil {
			if d, ok := routing["_default"]; ok && d.Provider != "" {
				provider = d.Provider
			}
		}
	}
	// has the user supplied their own key for that provider? -> self-funded, uncapped
	if rows, err := h.Q.ListUserProviderKeys(ctx, userID); err == nil {
		for _, row := range rows {
			if row.Provider == provider {
				return true, nil
			}
		}
	}
	spend, err := h.Q.UserOperatorSpend(ctx, userID)
	if err != nil {
		return true, nil // fail open — don't block on a query error
	}
	return spend < h.CapUSD, nil
}

// Create handles POST /goals (Flow A: pr_review, Flow B: issue_implement).
func (h *GoalsHandler) Create(w http.ResponseWriter, r *http.Request) {
	claims, _ := gwmw.ClaimsFromContext(r.Context())
	var req apitypes.CreateGoalRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respond.Error(w, r, http.StatusBadRequest, "BAD_REQUEST", "invalid body")
		return
	}

	// Demo budget gate: block once a user has spent the shared-key cap, unless
	// they've added their own API key (then it's their money — uncapped).
	if ok, _ := h.budgetAllowed(r.Context(), claims.UserID); !ok {
		respond.Error(w, r, http.StatusPaymentRequired, "BUDGET_EXCEEDED",
			"Demo budget reached — add your own API key in Settings to keep going.")
		return
	}

	var (
		owner, repo string
		number      int32
		issueNum    *int32
		prNum       *int32
		title       string
	)
	switch req.Type {
	case apitypes.GoalPRReview:
		m := prRe.FindStringSubmatch(req.PRURL)
		if m == nil {
			respond.Error(w, r, http.StatusBadRequest, "BAD_PR_URL", "could not parse PR URL")
			return
		}
		owner, repo = m[1], m[2]
		n, _ := strconv.Atoi(m[3])
		number = int32(n)
		prNum = &number
		title = fmt.Sprintf("Review %s/%s#%d", owner, repo, number)
	case apitypes.GoalIssueImplement:
		m := issueRe.FindStringSubmatch(req.IssueURL)
		if m == nil {
			respond.Error(w, r, http.StatusBadRequest, "BAD_ISSUE_URL", "could not parse issue URL")
			return
		}
		owner, repo = m[1], m[2]
		n, _ := strconv.Atoi(m[3])
		number = int32(n)
		issueNum = &number
		title = fmt.Sprintf("Resolve %s/%s#%d", owner, repo, number)
	default:
		respond.Error(w, r, http.StatusBadRequest, "BAD_TYPE", "unknown goal type")
		return
	}

	repoFull := owner + "/" + repo
	// fork_mode approximation for MVP: not the user's own repo -> fork-mode (deferred path).
	forkMode := !strings.EqualFold(owner, claims.GithubLogin)
	desc := req.Steer

	goal, err := h.Q.CreateGoal(r.Context(), store.CreateGoalParams{
		UserID:            claims.UserID,
		RepoFullName:      &repoFull,
		Type:              string(req.Type),
		Title:             title,
		Description:       &desc,
		GithubPrNumber:    prNum,
		GithubIssueNumber: issueNum,
		ForkMode:          forkMode,
	})
	if err != nil {
		h.Log.Error("create goal failed", "err", err)
		respond.Error(w, r, http.StatusInternalServerError, "DB_ERROR", "could not create goal")
		return
	}

	h.audit(r.Context(), "user", claims.UserID, "goal_created", goal.ID, map[string]any{
		"type": req.Type, "repo": repoFull, "number": number,
	})

	if err := h.Worker.SubmitGoal(r.Context(), goal.Uuid.String()); err != nil {
		h.Log.Error("submit goal to worker failed", "err", err)
		respond.Error(w, r, http.StatusBadGateway, "WORKER_UNAVAILABLE", "could not start goal")
		return
	}

	respond.JSON(w, r, http.StatusAccepted, map[string]string{"uuid": goal.Uuid.String()})
}

// List handles GET /goals.
func (h *GoalsHandler) List(w http.ResponseWriter, r *http.Request) {
	claims, _ := gwmw.ClaimsFromContext(r.Context())
	var status *string
	if s := r.URL.Query().Get("status"); s != "" {
		status = &s
	}
	rows, err := h.Q.ListGoalsByUser(r.Context(), store.ListGoalsByUserParams{
		UserID: claims.UserID, Status: status, Limit: 50, Offset: 0,
	})
	if err != nil {
		respond.Error(w, r, http.StatusInternalServerError, "DB_ERROR", err.Error())
		return
	}
	out := make([]apitypes.GoalSummary, 0, len(rows))
	for _, g := range rows {
		out = append(out, toSummary(g))
	}
	respond.OK(w, r, out)
}

// Get handles GET /goals/{uuid}.
func (h *GoalsHandler) Get(w http.ResponseWriter, r *http.Request) {
	id, err := uuid.Parse(chi.URLParam(r, "uuid"))
	if err != nil {
		respond.Error(w, r, http.StatusBadRequest, "BAD_UUID", "invalid uuid")
		return
	}
	goal, err := h.Q.GetGoalByUUID(r.Context(), id)
	if err != nil {
		respond.Error(w, r, http.StatusNotFound, "GOAL_NOT_FOUND", "goal not found")
		return
	}
	// Initialize as empty (non-nil) slices so JSON serializes [] not null — the
	// web client treats these as arrays (.find/.length/.reduce).
	detail := apitypes.GoalDetail{
		GoalSummary:   toSummary(goal),
		Description:   deref(goal.Description),
		Interrupts:    []apitypes.Interrupt{},
		Transcript:    []apitypes.CriticIteration{},
		CostBreakdown: []apitypes.CostRow{},
	}

	if ints, err := h.Q.ListInterruptsByGoal(r.Context(), goal.ID); err == nil {
		for _, it := range ints {
			var payload map[string]any
			_ = json.Unmarshal(it.PayloadJson, &payload)
			detail.Interrupts = append(detail.Interrupts, apitypes.Interrupt{
				UUID: it.Uuid.String(), Type: it.Type, Payload: payload,
				Decision: deref(it.Decision), ResolvedAt: it.ResolvedAt,
			})
		}
	}
	if iters, err := h.Q.ListCriticIterationsByGoal(r.Context(), goal.ID); err == nil {
		for _, ci := range iters {
			var fb map[string]any
			if ci.CriticFeedback != nil {
				_ = json.Unmarshal(ci.CriticFeedback, &fb)
			}
			var ss *float64
			if ci.SelfSatisfaction.Valid {
				if f, err := ci.SelfSatisfaction.Float64Value(); err == nil {
					v := f.Float64
					ss = &v
				}
			}
			detail.Transcript = append(detail.Transcript, apitypes.CriticIteration{
				Round: ci.RoundNumber, ImplementerDiff: deref(ci.ImplementerDiff),
				SelfSatisfaction: ss, CriticFeedback: fb,
			})
		}
	}
	if rows, err := h.Q.GoalCostBreakdown(r.Context(), goal.ID); err == nil {
		for _, c := range rows {
			detail.CostBreakdown = append(detail.CostBreakdown, apitypes.CostRow{
				Role: c.AgentRole, CallCount: c.CallCount,
				TokensIn: toInt64(c.TokensIn), TokensOut: toInt64(c.TokensOut),
				CachedTokens: toInt64(c.CachedTokens), CostUSD: toFloat64(c.CostUsd),
			})
		}
	}
	respond.OK(w, r, detail)
}

// Resume handles POST /goals/{uuid}/resume. For Flow A approve, it posts the
// review on GitHub as the user BEFORE telling the worker to resume.
func (h *GoalsHandler) Resume(w http.ResponseWriter, r *http.Request) {
	claims, _ := gwmw.ClaimsFromContext(r.Context())
	id, err := uuid.Parse(chi.URLParam(r, "uuid"))
	if err != nil {
		respond.Error(w, r, http.StatusBadRequest, "BAD_UUID", "invalid uuid")
		return
	}
	var req apitypes.ResumeRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respond.Error(w, r, http.StatusBadRequest, "BAD_REQUEST", "invalid body")
		return
	}
	goal, err := h.Q.GetGoalByUUID(r.Context(), id)
	if err != nil {
		respond.Error(w, r, http.StatusNotFound, "GOAL_NOT_FOUND", "goal not found")
		return
	}
	pending, err := h.Q.GetPendingInterrupt(r.Context(), goal.ID)
	if err != nil {
		respond.Error(w, r, http.StatusConflict, "NO_PENDING_GATE", "no pending gate")
		return
	}

	// Flow A: post the (edited) review as the user, before resuming the worker.
	if goal.Type == string(apitypes.GoalPRReview) && req.Decision == "approve" && req.EditedReview != nil {
		if err := h.postReview(r.Context(), claims.UserID, goal, req.EditedReview); err != nil {
			h.Log.Error("post review failed", "err", err)
			respond.Error(w, r, http.StatusBadGateway, "REVIEW_POST_FAILED", err.Error())
			return
		}
	}

	fb := req.Feedback
	_ = h.Q.ResolveInterrupt(r.Context(), store.ResolveInterruptParams{
		ID: pending.ID, Decision: &req.Decision, Feedback: &fb, ActorUserID: &claims.UserID,
	})
	h.audit(r.Context(), "user", claims.UserID, "cosign", goal.ID, map[string]any{
		"decision": req.Decision,
	})

	var editedJSON string
	if req.EditedReview != nil {
		b, _ := json.Marshal(req.EditedReview)
		editedJSON = string(b)
	}
	if err := h.Worker.ResumeFromInterrupt(r.Context(), goal.Uuid.String(), req.Decision, req.Feedback, editedJSON); err != nil {
		respond.Error(w, r, http.StatusBadGateway, "WORKER_UNAVAILABLE", "could not resume")
		return
	}
	respond.OK(w, r, map[string]bool{"ok": true})
}

// Cancel handles DELETE /goals/{uuid}.
func (h *GoalsHandler) Cancel(w http.ResponseWriter, r *http.Request) {
	id, err := uuid.Parse(chi.URLParam(r, "uuid"))
	if err != nil {
		respond.Error(w, r, http.StatusBadRequest, "BAD_UUID", "invalid uuid")
		return
	}
	goal, err := h.Q.GetGoalByUUID(r.Context(), id)
	if err != nil {
		respond.Error(w, r, http.StatusNotFound, "GOAL_NOT_FOUND", "goal not found")
		return
	}
	_ = h.Worker.CancelGoal(r.Context(), goal.Uuid.String())
	_ = h.Q.UpdateGoalStatus(r.Context(), store.UpdateGoalStatusParams{Uuid: id, Status: "cancelled"})
	respond.OK(w, r, map[string]bool{"ok": true})
}

// ── helpers ───────────────────────────────────────────────────────────────────
func (h *GoalsHandler) postReview(ctx context.Context, userID int64, goal store.Goal, draft *apitypes.ReviewDraft) error {
	row, err := h.Q.GetUserOAuthToken(ctx, userID)
	if err != nil {
		return fmt.Errorf("load token: %w", err)
	}
	tokenBytes, err := h.Crypto.Decrypt(row.GithubOauthTokenEncrypted)
	if err != nil {
		return fmt.Errorf("decrypt token: %w", err)
	}
	if goal.RepoFullName == nil || goal.GithubPrNumber == nil {
		return fmt.Errorf("goal missing repo/pr")
	}
	parts := strings.SplitN(*goal.RepoFullName, "/", 2)
	if len(parts) != 2 {
		return fmt.Errorf("bad repo full name")
	}
	ts := oauth2.StaticTokenSource(&oauth2.Token{AccessToken: string(tokenBytes)})
	gh := github.NewClient(oauth2.NewClient(ctx, ts))
	body := reviewMarkdown(draft)
	event := "COMMENT"
	_, _, err = gh.PullRequests.CreateReview(ctx, parts[0], parts[1], int(*goal.GithubPrNumber),
		&github.PullRequestReviewRequest{Body: &body, Event: &event})
	return err
}

func reviewMarkdown(d *apitypes.ReviewDraft) string {
	var b strings.Builder
	b.WriteString(strings.TrimSpace(d.Summary) + "\n\n")
	if len(d.AskChanges) > 0 {
		b.WriteString("**Requested changes**\n")
		for _, a := range d.AskChanges {
			b.WriteString("- " + a + "\n")
		}
		b.WriteString("\n")
	}
	if len(d.Praise) > 0 {
		b.WriteString("**Praise**\n")
		for _, p := range d.Praise {
			b.WriteString("- " + p + "\n")
		}
		b.WriteString("\n")
	}
	for _, c := range d.PerFileComments {
		loc := c.Path
		if c.Line > 0 {
			loc = fmt.Sprintf("%s:%d", c.Path, c.Line)
		}
		b.WriteString(fmt.Sprintf("- `%s` — %s\n", loc, c.Comment))
	}
	return b.String()
}

func (h *GoalsHandler) audit(ctx context.Context, actorType string, actorID int64, event string, goalID int64, payload map[string]any) {
	b, _ := json.Marshal(payload)
	sum := sha256.Sum256(b)
	hash := hex.EncodeToString(sum[:])
	_, _ = h.Q.InsertAuditLog(ctx, store.InsertAuditLogParams{
		ActorType: actorType, ActorID: &actorID, EventType: event,
		GoalID: &goalID, PayloadJson: b, PayloadHash: &hash,
	})
}

func toSummary(g store.Goal) apitypes.GoalSummary {
	s := apitypes.GoalSummary{
		UUID: g.Uuid.String(), Type: apitypes.GoalType(g.Type), Title: g.Title,
		Status: g.Status, RepoFull: deref(g.RepoFullName), ForkMode: g.ForkMode,
		PRNumber: g.GithubPrNumber, IssueNumber: g.GithubIssueNumber,
	}
	if g.CreatedAt.Valid {
		s.CreatedAt = g.CreatedAt.Time
	}
	s.CompletedAt = g.CompletedAt
	return s
}

func deref[T any](p *T) T {
	if p == nil {
		var zero T
		return zero
	}
	return *p
}

// COALESCE/SUM aggregates come back as interface{}; coerce robustly.
func toInt64(v any) int64 {
	switch n := v.(type) {
	case int64:
		return n
	case int32:
		return int64(n)
	case float64:
		return int64(n)
	default:
		i, _ := strconv.ParseInt(fmt.Sprint(v), 10, 64)
		return i
	}
}

func toFloat64(v any) float64 {
	switch n := v.(type) {
	case float64:
		return n
	case int64:
		return float64(n)
	default:
		f, _ := strconv.ParseFloat(fmt.Sprint(v), 64)
		return f
	}
}
