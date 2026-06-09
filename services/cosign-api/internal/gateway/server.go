// Package gateway wires the chi HTTP router: middleware + routes.
package gateway

import (
	"log/slog"
	"net/http"

	"github.com/go-chi/chi/v5"
	chimw "github.com/go-chi/chi/v5/middleware"
	"github.com/go-chi/cors"
	"github.com/tensor-bloom/cosign/services/cosign-api/internal/gateway/handlers"
	gwmw "github.com/tensor-bloom/cosign/services/cosign-api/internal/gateway/middleware"
	"github.com/tensor-bloom/cosign/services/cosign-api/internal/gateway/sse"
	"github.com/tensor-bloom/cosign/services/cosign-api/internal/identity"
)

type Deps struct {
	Log        *slog.Logger
	Tokens     *identity.TokenManager
	Health     handlers.HealthHandler
	Auth       *handlers.AuthHandler
	Goals      *handlers.GoalsHandler
	Settings   *handlers.SettingsHandler
	SSE        *sse.Handler
	WebBaseURL string
}

// NewRouter builds the HTTP handler for cosign-api.
func NewRouter(d Deps) http.Handler {
	r := chi.NewRouter()

	r.Use(chimw.RequestID)
	r.Use(chimw.Recoverer)
	r.Use(gwmw.AccessLog(d.Log))
	r.Use(cors.Handler(cors.Options{
		AllowedOrigins:   []string{d.WebBaseURL},
		AllowedMethods:   []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"},
		AllowedHeaders:   []string{"Content-Type", "Authorization", "Last-Event-ID"},
		AllowCredentials: true,
		MaxAge:           300,
	}))

	// Public
	r.Get("/health", d.Health.Health)

	r.Route("/auth", func(r chi.Router) {
		r.Get("/github/login", d.Auth.Login)
		r.Get("/github/callback", d.Auth.Callback)
		r.Get("/github/install", d.Auth.Install)
		r.Post("/logout", d.Auth.Logout)
		// authenticated
		r.Group(func(r chi.Router) {
			r.Use(gwmw.Auth(d.Tokens))
			r.Get("/me", d.Auth.Me)
		})
	})

	// Protected API surface
	r.Group(func(r chi.Router) {
		r.Use(gwmw.Auth(d.Tokens))
		r.Post("/goals", d.Goals.Create)
		r.Get("/goals", d.Goals.List)
		r.Get("/goals/{uuid}", d.Goals.Get)
		r.Post("/goals/{uuid}/resume", d.Goals.Resume)
		r.Delete("/goals/{uuid}", d.Goals.Cancel)

		r.Get("/settings", d.Settings.Get)
		r.Put("/settings/routing", d.Settings.PutRouting)
		r.Put("/settings/keys", d.Settings.PutKey)
	})

	// SSE stream (auth via cookie; EventSource can't set headers).
	r.Group(func(r chi.Router) {
		r.Use(gwmw.Auth(d.Tokens))
		r.Get("/stream/goals/{uuid}", d.SSE.StreamGoal)
	})

	return r
}
