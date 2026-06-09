// Package respond writes the standard { data, meta, error } envelope.
package respond

import (
	"encoding/json"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5/middleware"
	"github.com/tensor-bloom/cosign/services/cosign-api/pkg/apitypes"
)

func meta(r *http.Request) apitypes.Meta {
	return apitypes.Meta{
		RequestID: middleware.GetReqID(r.Context()),
		Timestamp: time.Now().UTC().Format(time.RFC3339Nano),
	}
}

// OK writes a 200 with data.
func OK(w http.ResponseWriter, r *http.Request, data any) {
	JSON(w, r, http.StatusOK, data)
}

// JSON writes an arbitrary status with data and a null error.
func JSON(w http.ResponseWriter, r *http.Request, status int, data any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(apitypes.Envelope{
		Data: data,
		Meta: meta(r),
	})
}

// Error writes an error envelope.
func Error(w http.ResponseWriter, r *http.Request, status int, code, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(apitypes.Envelope{
		Meta:  meta(r),
		Error: &apitypes.APIError{Code: code, Message: message},
	})
}
