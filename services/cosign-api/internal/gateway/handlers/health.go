// Package handlers holds cosign-api HTTP handlers.
package handlers

import (
	"net/http"

	"github.com/tensor-bloom/cosign/services/cosign-api/internal/gateway/respond"
)

type HealthHandler struct {
	Version string
	Commit  string
}

func (h HealthHandler) Health(w http.ResponseWriter, r *http.Request) {
	respond.OK(w, r, map[string]string{
		"status":  "ok",
		"version": h.Version,
		"commit":  h.Commit,
	})
}
