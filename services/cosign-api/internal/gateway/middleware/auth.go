// Package middleware holds cosign-api HTTP middleware: access logging and the
// JWT session auth gate. (request_id / recovery / cors come from chi + go-chi/cors.)
package middleware

import (
	"context"
	"net/http"

	"github.com/tensor-bloom/cosign/services/cosign-api/internal/gateway/respond"
	"github.com/tensor-bloom/cosign/services/cosign-api/internal/identity"
)

// SessionCookieName is the HttpOnly cookie holding the RS256 session JWT.
const SessionCookieName = "cosign_session"

type ctxKey int

const claimsKey ctxKey = iota

// Auth verifies the session cookie and injects claims into the request context.
// Returns 401 when absent/invalid.
func Auth(tm *identity.TokenManager) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			cookie, err := r.Cookie(SessionCookieName)
			if err != nil {
				respond.Error(w, r, http.StatusUnauthorized, "UNAUTHENTICATED", "no session")
				return
			}
			claims, err := tm.Parse(cookie.Value)
			if err != nil {
				respond.Error(w, r, http.StatusUnauthorized, "UNAUTHENTICATED", "invalid session")
				return
			}
			ctx := context.WithValue(r.Context(), claimsKey, claims)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

// ClaimsFromContext returns the authenticated user's claims, if present.
func ClaimsFromContext(ctx context.Context) (*identity.Claims, bool) {
	c, ok := ctx.Value(claimsKey).(*identity.Claims)
	return c, ok
}
