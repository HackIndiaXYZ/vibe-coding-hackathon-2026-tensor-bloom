// Command cosign-api is the Go HTTP gateway + identity gRPC server.
package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"
	"google.golang.org/grpc"

	"github.com/tensor-bloom/cosign/services/cosign-api/internal/config"
	"github.com/tensor-bloom/cosign/services/cosign-api/internal/gateway"
	"github.com/tensor-bloom/cosign/services/cosign-api/internal/gateway/handlers"
	"github.com/tensor-bloom/cosign/services/cosign-api/internal/gateway/sse"
	"github.com/tensor-bloom/cosign/services/cosign-api/internal/identity"
	"github.com/tensor-bloom/cosign/services/cosign-api/internal/orchestration"
	"github.com/tensor-bloom/cosign/services/cosign-api/internal/pb"
	"github.com/tensor-bloom/cosign/services/cosign-api/internal/store"
)

// build info (set via -ldflags)
var (
	version = "dev"
	commit  = "none"
)

func main() {
	// `cosign-api healthcheck` is used by the Docker HEALTHCHECK.
	if len(os.Args) > 1 && os.Args[1] == "healthcheck" {
		healthcheck()
		return
	}
	// `cosign-api mint-token <user_id> <login> <uuid>` — dev-only helper to mint a
	// session JWT for local testing (no live OAuth). Reads the JWT key from env.
	if len(os.Args) > 1 && os.Args[1] == "mint-token" {
		mintToken(os.Args[2:])
		return
	}
	if err := run(); err != nil {
		slog.Error("fatal", "err", err)
		os.Exit(1)
	}
}

func run() error {
	cfg, err := config.Load()
	if err != nil {
		return err
	}
	cfg.Version, cfg.Commit = version, commit
	log := newLogger(cfg)

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	// Stores
	pool, err := pgxpool.New(ctx, cfg.DatabaseURL)
	if err != nil {
		return err
	}
	defer pool.Close()
	if err := pool.Ping(ctx); err != nil {
		return err
	}
	q := store.New(pool)

	// Redis (SSE fan-out + sessions)
	ropts, err := redis.ParseURL(cfg.RedisURL)
	if err != nil {
		return err
	}
	rdb := redis.NewClient(ropts)
	defer rdb.Close()

	// Worker orchestration gRPC client
	worker, err := orchestration.Dial(cfg.WorkerGRPCAddr)
	if err != nil {
		return err
	}
	defer worker.Close()

	// Identity primitives
	crypto, err := identity.NewCrypto(cfg.OAuthEncKeyB64)
	if err != nil {
		return err
	}
	tokens, err := identity.NewTokenManager(cfg.JWTPrivateKeyPath, cfg.JWTPublicKeyPath)
	if err != nil {
		return err
	}

	// HTTP server
	authH := handlers.NewAuthHandler(q, crypto, tokens, log,
		cfg.GithubClientID, cfg.GithubClientSecret, cfg.GithubRedirectURL,
		cfg.WebBaseURL, cfg.GithubAppInstallURL, cfg.CookieSecure, cfg.CookieDomain)

	goalsH := &handlers.GoalsHandler{
		Q: q, Crypto: crypto, Worker: worker, Log: log,
		CapUSD: cfg.DemoUserCapUSD, DefaultProvider: cfg.DemoDefaultProvider,
	}
	settingsH := &handlers.SettingsHandler{
		Q: q, Crypto: crypto, Log: log,
		CapUSD: cfg.DemoUserCapUSD, DefaultProvider: cfg.DemoDefaultProvider, DefaultModel: cfg.DemoDefaultModel,
	}
	sseH := &sse.Handler{Redis: rdb, Log: log}

	router := gateway.NewRouter(gateway.Deps{
		Log:        log,
		Tokens:     tokens,
		Health:     handlers.HealthHandler{Version: version, Commit: commit},
		Auth:       authH,
		Goals:      goalsH,
		Settings:   settingsH,
		SSE:        sseH,
		WebBaseURL: cfg.WebBaseURL,
	})
	httpSrv := &http.Server{
		Addr:              cfg.HTTPListenAddr,
		Handler:           router,
		ReadHeaderTimeout: 10 * time.Second,
	}

	// gRPC identity server
	grpcSrv := grpc.NewServer()
	pb.RegisterIdentityServiceServer(grpcSrv, &identity.GRPCServer{Q: q, Crypto: crypto, Log: log})
	grpcLis, err := net.Listen("tcp", cfg.APIGRPCListenAddr)
	if err != nil {
		return err
	}

	errCh := make(chan error, 2)
	go func() {
		log.Info("http listening", "addr", cfg.HTTPListenAddr)
		if err := httpSrv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			errCh <- err
		}
	}()
	go func() {
		log.Info("grpc identity listening", "addr", cfg.APIGRPCListenAddr)
		if err := grpcSrv.Serve(grpcLis); err != nil {
			errCh <- err
		}
	}()

	select {
	case <-ctx.Done():
		log.Info("shutting down")
	case err := <-errCh:
		log.Error("server error", "err", err)
	}

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	_ = httpSrv.Shutdown(shutdownCtx)
	grpcSrv.GracefulStop()
	return nil
}

func newLogger(cfg *config.Config) *slog.Logger {
	level := slog.LevelInfo
	switch cfg.LogLevel {
	case "debug":
		level = slog.LevelDebug
	case "warn":
		level = slog.LevelWarn
	case "error":
		level = slog.LevelError
	}
	opts := &slog.HandlerOptions{Level: level}
	var h slog.Handler = slog.NewJSONHandler(os.Stdout, opts)
	if cfg.LogFormat == "text" {
		h = slog.NewTextHandler(os.Stdout, opts)
	}
	return slog.New(h)
}

// mintToken prints a session JWT for a user (dev/testing only).
func mintToken(args []string) {
	if len(args) < 3 {
		fmt.Fprintln(os.Stderr, "usage: cosign-api mint-token <user_id> <login> <uuid>")
		os.Exit(2)
	}
	uid, _ := strconv.ParseInt(args[0], 10, 64)
	tm, err := identity.NewTokenManager(
		os.Getenv("JWT_RSA_PRIVATE_KEY_PATH"), os.Getenv("JWT_RSA_PUBLIC_KEY_PATH"))
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	tok, err := tm.Issue(uid, args[1], args[2])
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	fmt.Println(tok)
}

// healthcheck hits the local /health endpoint; exit 0 = healthy.
func healthcheck() {
	addr := os.Getenv("HTTP_LISTEN_ADDR")
	if addr == "" {
		addr = ":8080"
	}
	url := "http://localhost" + addr + "/health"
	client := &http.Client{Timeout: 3 * time.Second}
	resp, err := client.Get(url)
	if err != nil || resp.StatusCode != http.StatusOK {
		os.Exit(1)
	}
	os.Exit(0)
}
