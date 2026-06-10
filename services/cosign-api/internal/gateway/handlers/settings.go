package handlers

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"slices"

	gwmw "github.com/tensor-bloom/cosign/services/cosign-api/internal/gateway/middleware"
	"github.com/tensor-bloom/cosign/services/cosign-api/internal/gateway/respond"
	"github.com/tensor-bloom/cosign/services/cosign-api/internal/identity"
	"github.com/tensor-bloom/cosign/services/cosign-api/internal/store"
	"github.com/tensor-bloom/cosign/services/cosign-api/pkg/apitypes"
)

// SettingsHandler manages per-user LLM routing + BYO provider keys.
// GET never returns key material; keys are only decrypted worker-side over gRPC.
type SettingsHandler struct {
	Q               *store.Queries
	Crypto          *identity.Crypto
	Log             *slog.Logger
	CapUSD          float64
	DefaultProvider string
	DefaultModel    string
}

func (h *SettingsHandler) Get(w http.ResponseWriter, r *http.Request) {
	claims, _ := gwmw.ClaimsFromContext(r.Context())

	routing := map[string]apitypes.RouteChoice{}
	if raw, err := h.Q.GetUserRouting(r.Context(), claims.UserID); err == nil && len(raw) > 0 {
		_ = json.Unmarshal(raw, &routing)
	}

	have := map[string]bool{}
	if rows, err := h.Q.ListUserProviderKeys(r.Context(), claims.UserID); err == nil {
		for _, row := range rows {
			have[row.Provider] = true
		}
	}
	providers := make([]apitypes.ProviderStatus, 0, len(apitypes.KnownProviders))
	for _, p := range apitypes.KnownProviders {
		providers = append(providers, apitypes.ProviderStatus{Name: p, HasKey: have[p]})
	}

	// Demo budget surface: effective default provider, whether the user self-funds
	// it, and their operator-funded spend so far.
	effProvider := h.DefaultProvider
	if d, ok := routing["_default"]; ok && d.Provider != "" {
		effProvider = d.Provider
	}
	usingOwnKey := have[effProvider]
	var usage float64
	if h.CapUSD > 0 {
		usage, _ = h.Q.UserOperatorSpend(r.Context(), claims.UserID)
	}

	respond.OK(w, r, apitypes.SettingsResponse{
		Routing:            routing,
		Providers:          providers,
		Catalog:            apitypes.Catalog,
		Roles:              apitypes.Roles,
		DefaultModel:       h.DefaultModel,
		SharedKeyAvailable: h.CapUSD > 0,
		CapUSD:             h.CapUSD,
		UsageUSD:           usage,
		UsingOwnKey:        usingOwnKey,
	})
}

func (h *SettingsHandler) PutRouting(w http.ResponseWriter, r *http.Request) {
	claims, _ := gwmw.ClaimsFromContext(r.Context())
	var req apitypes.PutRoutingRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respond.Error(w, r, http.StatusBadRequest, "BAD_REQUEST", "invalid body")
		return
	}
	// drop empty selections so the worker falls back to operator config
	for k, v := range req.Routing {
		if v.Provider == "" || v.Model == "" {
			delete(req.Routing, k)
		}
	}
	blob, _ := json.Marshal(req.Routing)
	if err := h.Q.UpsertUserRouting(r.Context(), store.UpsertUserRoutingParams{
		UserID: claims.UserID, RoutingJson: blob,
	}); err != nil {
		respond.Error(w, r, http.StatusInternalServerError, "DB_ERROR", err.Error())
		return
	}
	h.audit(r.Context(), claims.UserID, "settings_routing_updated", map[string]any{"roles": len(req.Routing)})
	respond.OK(w, r, map[string]bool{"ok": true})
}

func (h *SettingsHandler) PutKey(w http.ResponseWriter, r *http.Request) {
	claims, _ := gwmw.ClaimsFromContext(r.Context())
	var req apitypes.PutKeyRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respond.Error(w, r, http.StatusBadRequest, "BAD_REQUEST", "invalid body")
		return
	}
	if !slices.Contains(apitypes.KnownProviders, req.Provider) {
		respond.Error(w, r, http.StatusBadRequest, "UNKNOWN_PROVIDER", "unknown provider")
		return
	}
	if req.APIKey == "" {
		_ = h.Q.DeleteUserProviderKey(r.Context(), store.DeleteUserProviderKeyParams{
			UserID: claims.UserID, Provider: req.Provider,
		})
		h.audit(r.Context(), claims.UserID, "settings_key_deleted", map[string]any{"provider": req.Provider})
		respond.OK(w, r, map[string]bool{"ok": true})
		return
	}
	enc, err := h.Crypto.Encrypt([]byte(req.APIKey))
	if err != nil {
		respond.Error(w, r, http.StatusInternalServerError, "ENCRYPT_FAILED", "could not encrypt key")
		return
	}
	if err := h.Q.UpsertUserProviderKey(r.Context(), store.UpsertUserProviderKeyParams{
		UserID: claims.UserID, Provider: req.Provider, ApiKeyEncrypted: enc,
	}); err != nil {
		respond.Error(w, r, http.StatusInternalServerError, "DB_ERROR", err.Error())
		return
	}
	h.audit(r.Context(), claims.UserID, "settings_key_set", map[string]any{"provider": req.Provider})
	respond.OK(w, r, map[string]bool{"ok": true})
}

func (h *SettingsHandler) audit(ctx context.Context, userID int64, event string, payload map[string]any) {
	b, _ := json.Marshal(payload)
	_, _ = h.Q.InsertAuditLog(ctx, store.InsertAuditLogParams{
		ActorType: "user", ActorID: &userID, EventType: event, PayloadJson: b,
	})
}
