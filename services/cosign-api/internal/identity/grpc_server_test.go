package identity

import (
	"context"
	"crypto/rand"
	"encoding/base64"
	"os"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/tensor-bloom/cosign/services/cosign-api/internal/pb"
	"github.com/tensor-bloom/cosign/services/cosign-api/internal/store"
)

// dbURL returns the test DB URL, or "" to skip (no DB available).
func dbURL() string {
	if v := os.Getenv("TEST_DATABASE_URL"); v != "" {
		return v
	}
	return "postgres://cosign:changeme@localhost:5432/cosign?sslmode=disable"
}

func newServer(t *testing.T) (*GRPCServer, *store.Queries, func()) {
	t.Helper()
	pool, err := pgxpool.New(context.Background(), dbURL())
	if err != nil {
		t.Skipf("no DB: %v", err)
	}
	if err := pool.Ping(context.Background()); err != nil {
		pool.Close()
		t.Skipf("DB unreachable: %v", err)
	}
	key := make([]byte, 32)
	_, _ = rand.Read(key)
	crypto, _ := NewCrypto(base64.StdEncoding.EncodeToString(key))
	q := store.New(pool)
	return &GRPCServer{Q: q, Crypto: crypto}, q, pool.Close
}

func TestGetUserOAuthTokenRoundTrip(t *testing.T) {
	srv, q, closeFn := newServer(t)
	defer closeFn()
	ctx := context.Background()

	const tokenPlain = "gho_grpc_roundtrip_token"
	enc, err := srv.Crypto.Encrypt([]byte(tokenPlain))
	if err != nil {
		t.Fatalf("encrypt: %v", err)
	}
	// unique github_id to avoid collisions across runs
	user, err := q.UpsertUser(ctx, store.UpsertUserParams{
		GithubID:                  990000001,
		GithubLogin:               "grpc-test-user",
		GithubOauthTokenEncrypted: enc,
	})
	if err != nil {
		t.Fatalf("upsert: %v", err)
	}

	resp, err := srv.GetUserOAuthToken(ctx, &pb.GetUserOAuthTokenRequest{UserId: user.ID})
	if err != nil {
		t.Fatalf("GetUserOAuthToken: %v", err)
	}
	if resp.OauthToken != tokenPlain {
		t.Fatalf("token mismatch: got %q want %q", resp.OauthToken, tokenPlain)
	}
	if resp.GithubLogin != "grpc-test-user" {
		t.Fatalf("login mismatch: %q", resp.GithubLogin)
	}
}

func TestVerifyCapability(t *testing.T) {
	srv, _, closeFn := newServer(t)
	defer closeFn()
	ctx := context.Background()

	// agent id 1 = implementer (seeded), has code_exec
	ok, err := srv.VerifyCapability(ctx, &pb.VerifyCapabilityRequest{AgentId: 1, ToolName: "code_exec"})
	if err != nil {
		t.Fatalf("VerifyCapability: %v", err)
	}
	if !ok.Allowed {
		t.Fatalf("expected code_exec allowed for implementer, got: %s", ok.Reason)
	}

	denied, err := srv.VerifyCapability(ctx, &pb.VerifyCapabilityRequest{AgentId: 1, ToolName: "no_such_tool"})
	if err != nil {
		t.Fatalf("VerifyCapability: %v", err)
	}
	if denied.Allowed {
		t.Fatal("expected no_such_tool denied")
	}
}
