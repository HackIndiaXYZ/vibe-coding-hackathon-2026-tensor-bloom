package identity

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"log/slog"

	"github.com/google/uuid"
	"github.com/tensor-bloom/cosign/services/cosign-api/internal/pb"
	"github.com/tensor-bloom/cosign/services/cosign-api/internal/store"
)

// GRPCServer implements the IdentityService the worker calls (ARCHITECTURE §9.2, §7.1).
type GRPCServer struct {
	pb.UnimplementedIdentityServiceServer
	Q      *store.Queries
	Crypto *Crypto
	Log    *slog.Logger
}

type agentCapabilities struct {
	Tools []string `json:"tools"`
}

// VerifyCapability checks a per-agent tool allowlist.
func (s *GRPCServer) VerifyCapability(ctx context.Context, req *pb.VerifyCapabilityRequest) (*pb.VerifyCapabilityResponse, error) {
	agent, err := s.Q.GetAgentByID(ctx, req.AgentId)
	if err != nil {
		return &pb.VerifyCapabilityResponse{Allowed: false, Reason: "agent not found"}, nil
	}
	var caps agentCapabilities
	if err := json.Unmarshal(agent.Capabilities, &caps); err != nil {
		return &pb.VerifyCapabilityResponse{Allowed: false, Reason: "bad capabilities json"}, nil
	}
	for _, t := range caps.Tools {
		if t == req.ToolName || t == "*" {
			return &pb.VerifyCapabilityResponse{Allowed: true}, nil
		}
	}
	return &pb.VerifyCapabilityResponse{Allowed: false, Reason: "tool not in agent allowlist"}, nil
}

// GetUserOAuthToken decrypts + returns the user's GitHub OAuth token so the
// worker can act AS the user (never a bot).
func (s *GRPCServer) GetUserOAuthToken(ctx context.Context, req *pb.GetUserOAuthTokenRequest) (*pb.GetUserOAuthTokenResponse, error) {
	row, err := s.Q.GetUserOAuthToken(ctx, req.UserId)
	if err != nil {
		return nil, err
	}
	plain, err := s.Crypto.Decrypt(row.GithubOauthTokenEncrypted)
	if err != nil {
		return nil, err
	}
	return &pb.GetUserOAuthTokenResponse{
		OauthToken:  string(plain),
		GithubLogin: row.GithubLogin,
	}, nil
}

// GetUserLLMSettings returns the user's routing overrides + decrypted provider
// keys (BYO). Same trust boundary as GetUserOAuthToken.
func (s *GRPCServer) GetUserLLMSettings(ctx context.Context, req *pb.GetUserLLMSettingsRequest) (*pb.GetUserLLMSettingsResponse, error) {
	resp := &pb.GetUserLLMSettingsResponse{ProviderKeys: map[string]string{}}
	if raw, err := s.Q.GetUserRouting(ctx, req.UserId); err == nil && len(raw) > 0 {
		resp.RoutingJson = string(raw)
	} else {
		resp.RoutingJson = "{}"
	}
	rows, err := s.Q.ListUserProviderKeys(ctx, req.UserId)
	if err != nil {
		return resp, nil // no keys is fine
	}
	for _, row := range rows {
		plain, err := s.Crypto.Decrypt(row.ApiKeyEncrypted)
		if err != nil {
			s.Log.Warn("decrypt provider key failed", "provider", row.Provider, "err", err)
			continue
		}
		resp.ProviderKeys[row.Provider] = string(plain)
	}
	return resp, nil
}

// EmitAuditLog appends an audit row.
func (s *GRPCServer) EmitAuditLog(ctx context.Context, req *pb.EmitAuditLogRequest) (*pb.EmitAuditLogResponse, error) {
	var goalID *int64
	if req.GoalUuid != "" {
		if u, err := uuid.Parse(req.GoalUuid); err == nil {
			if g, err := s.Q.GetGoalByUUID(ctx, u); err == nil {
				goalID = &g.ID
			}
		}
	}
	sum := sha256.Sum256([]byte(req.PayloadJson))
	hash := hex.EncodeToString(sum[:])

	var actorID *int64
	if req.ActorId != 0 {
		actorID = &req.ActorId
	}
	_, err := s.Q.InsertAuditLog(ctx, store.InsertAuditLogParams{
		ActorType:   req.ActorType,
		ActorID:     actorID,
		EventType:   req.EventType,
		GoalID:      goalID,
		PayloadJson: []byte(req.PayloadJson),
		PayloadHash: &hash,
	})
	if err != nil {
		return &pb.EmitAuditLogResponse{Ok: false}, err
	}
	return &pb.EmitAuditLogResponse{Ok: true}, nil
}
