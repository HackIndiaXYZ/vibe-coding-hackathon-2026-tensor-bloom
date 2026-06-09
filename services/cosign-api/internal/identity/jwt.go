package identity

import (
	"crypto/rsa"
	"fmt"
	"os"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

// TokenManager signs + verifies RS256 session JWTs.
type TokenManager struct {
	priv *rsa.PrivateKey
	pub  *rsa.PublicKey
	ttl  time.Duration
}

// Claims is the session token payload.
type Claims struct {
	UserID      int64  `json:"uid"`
	GithubLogin string `json:"login"`
	jwt.RegisteredClaims
}

func NewTokenManager(privPath, pubPath string) (*TokenManager, error) {
	privPEM, err := os.ReadFile(privPath)
	if err != nil {
		return nil, fmt.Errorf("read jwt private key: %w", err)
	}
	priv, err := jwt.ParseRSAPrivateKeyFromPEM(privPEM)
	if err != nil {
		return nil, fmt.Errorf("parse jwt private key: %w", err)
	}
	pubPEM, err := os.ReadFile(pubPath)
	if err != nil {
		return nil, fmt.Errorf("read jwt public key: %w", err)
	}
	pub, err := jwt.ParseRSAPublicKeyFromPEM(pubPEM)
	if err != nil {
		return nil, fmt.Errorf("parse jwt public key: %w", err)
	}
	return &TokenManager{priv: priv, pub: pub, ttl: 24 * time.Hour}, nil
}

func (t *TokenManager) Issue(userID int64, login, userUUID string) (string, error) {
	now := time.Now()
	claims := Claims{
		UserID:      userID,
		GithubLogin: login,
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   userUUID,
			IssuedAt:  jwt.NewNumericDate(now),
			ExpiresAt: jwt.NewNumericDate(now.Add(t.ttl)),
			Issuer:    "cosign-api",
		},
	}
	return jwt.NewWithClaims(jwt.SigningMethodRS256, claims).SignedString(t.priv)
}

func (t *TokenManager) Parse(raw string) (*Claims, error) {
	var claims Claims
	_, err := jwt.ParseWithClaims(raw, &claims, func(tok *jwt.Token) (any, error) {
		if _, ok := tok.Method.(*jwt.SigningMethodRSA); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", tok.Header["alg"])
		}
		return t.pub, nil
	})
	if err != nil {
		return nil, err
	}
	return &claims, nil
}

func (t *TokenManager) TTL() time.Duration { return t.ttl }
