// Package sse fans out worker events (Redis Streams) to browsers over SSE
// (ARCHITECTURE §1.2, §8.3).
package sse

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/redis/go-redis/v9"
)

type Handler struct {
	Redis *redis.Client
	Log   *slog.Logger
}

// StreamGoal handles GET /stream/goals/{uuid}. It reads stream:goal:{uuid} and
// forwards each entry as an SSE event, honoring Last-Event-ID for reconnect and
// sending a heartbeat every 15s.
func (h *Handler) StreamGoal(w http.ResponseWriter, r *http.Request) {
	goalUUID := chi.URLParam(r, "uuid")
	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "streaming unsupported", http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("X-Accel-Buffering", "no")

	// Start from Last-Event-ID if reconnecting, else from the beginning so the
	// client gets the current state of an in-flight goal.
	lastID := r.Header.Get("Last-Event-ID")
	if lastID == "" {
		lastID = "0"
	}
	streamKey := "stream:goal:" + goalUUID
	ctx := r.Context()

	for {
		select {
		case <-ctx.Done():
			return
		default:
		}

		res, err := h.Redis.XRead(ctx, &redis.XReadArgs{
			Streams: []string{streamKey, lastID},
			Block:   15 * time.Second,
			Count:   50,
		}).Result()
		if err == redis.Nil || (err != nil && err == context.DeadlineExceeded) {
			fmt.Fprint(w, ": ping\n\n") // heartbeat
			flusher.Flush()
			continue
		}
		if err != nil {
			if ctx.Err() != nil {
				return
			}
			// transient: heartbeat and retry
			fmt.Fprint(w, ": ping\n\n")
			flusher.Flush()
			continue
		}
		for _, stream := range res {
			for _, msg := range stream.Messages {
				lastID = msg.ID
				event, _ := msg.Values["event"].(string)
				data, _ := msg.Values["data"].(string)
				if event == "" {
					event = "message"
				}
				fmt.Fprintf(w, "id: %s\nevent: %s\ndata: %s\n\n", msg.ID, event, data)
				flusher.Flush()
			}
		}
	}
}
