// Package config loads + validates cosign-api configuration from the environment.
package config

import (
	"fmt"

	"github.com/kelseyhightower/envconfig"
)

type Config struct {
	// HTTP / gRPC listeners
	HTTPListenAddr     string `envconfig:"HTTP_LISTEN_ADDR" default:":8080"`
	APIGRPCListenAddr  string `envconfig:"API_GRPC_LISTEN_ADDR" default:":50051"`
	WorkerGRPCAddr     string `envconfig:"WORKER_GRPC_ADDR" default:"cosign-worker:50052"`

	// Stores
	DatabaseURL string `envconfig:"DATABASE_URL" required:"true"`
	RedisURL    string `envconfig:"REDIS_URL" default:"redis://redis:6379"`

	// GitHub OAuth
	GithubClientID     string `envconfig:"GITHUB_OAUTH_CLIENT_ID"`
	GithubClientSecret string `envconfig:"GITHUB_OAUTH_CLIENT_SECRET"`
	GithubRedirectURL  string `envconfig:"GITHUB_OAUTH_REDIRECT_URL" default:"http://localhost:8080/auth/github/callback"`
	GithubAppInstallURL string `envconfig:"GITHUB_APP_INSTALL_URL"`

	// JWT (RS256) + token encryption
	JWTPrivateKeyPath string `envconfig:"JWT_RSA_PRIVATE_KEY_PATH" required:"true"`
	JWTPublicKeyPath  string `envconfig:"JWT_RSA_PUBLIC_KEY_PATH" required:"true"`
	OAuthEncKeyB64    string `envconfig:"OAUTH_TOKEN_ENCRYPTION_KEY" required:"true"`

	// Web app origin (CORS + post-login redirect)
	WebBaseURL string `envconfig:"WEB_BASE_URL" default:"http://localhost:3000"`

	// Demo budget: per-user lifetime cap (USD) on the SHARED operator LLM key.
	// 0 = disabled (no cap, e.g. local dev). Users with their own key are uncapped.
	DemoUserCapUSD      float64 `envconfig:"DEMO_USER_CAP_USD" default:"0"`
	DemoDefaultProvider string  `envconfig:"DEMO_DEFAULT_PROVIDER" default:"anthropic"`
	DemoDefaultModel    string  `envconfig:"DEMO_DEFAULT_MODEL" default:"anthropic/claude-haiku-4-5-20251001"`

	// Cookies
	CookieSecure bool   `envconfig:"COOKIE_SECURE" default:"false"`
	CookieDomain string `envconfig:"COOKIE_DOMAIN" default:""`

	// Observability
	LogLevel  string `envconfig:"LOG_LEVEL" default:"info"`
	LogFormat string `envconfig:"LOG_FORMAT" default:"json"`

	// Build info (ldflags)
	Version string `envconfig:"-"`
	Commit  string `envconfig:"-"`
}

func Load() (*Config, error) {
	var c Config
	if err := envconfig.Process("", &c); err != nil {
		return nil, fmt.Errorf("load config: %w", err)
	}
	return &c, nil
}
