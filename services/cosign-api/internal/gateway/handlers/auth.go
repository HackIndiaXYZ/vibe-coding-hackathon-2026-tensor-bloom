package handlers

import (
	"crypto/rand"
	"encoding/base64"
	"fmt"
	"log/slog"
	"net/http"
	"time"

	"github.com/google/go-github/v66/github"
	gwmw "github.com/tensor-bloom/cosign/services/cosign-api/internal/gateway/middleware"
	"github.com/tensor-bloom/cosign/services/cosign-api/internal/gateway/respond"
	"github.com/tensor-bloom/cosign/services/cosign-api/internal/identity"
	"github.com/tensor-bloom/cosign/services/cosign-api/internal/store"
	"github.com/tensor-bloom/cosign/services/cosign-api/pkg/apitypes"
	"golang.org/x/oauth2"
	githuboauth "golang.org/x/oauth2/github"
)

const oauthStateCookie = "cosign_oauth_state"

// AuthHandler implements the GitHub OAuth login dance + session management.
type AuthHandler struct {
	Q            *store.Queries
	Crypto       *identity.Crypto
	Tokens       *identity.TokenManager
	Log          *slog.Logger
	WebBaseURL   string
	InstallURL   string
	CookieSecure bool
	CookieDomain string
	oauthCfg     *oauth2.Config
}

func NewAuthHandler(q *store.Queries, c *identity.Crypto, tm *identity.TokenManager, log *slog.Logger,
	clientID, clientSecret, redirectURL, webBaseURL, installURL string, cookieSecure bool, cookieDomain string) *AuthHandler {
	return &AuthHandler{
		Q: q, Crypto: c, Tokens: tm, Log: log,
		WebBaseURL: webBaseURL, InstallURL: installURL,
		CookieSecure: cookieSecure, CookieDomain: cookieDomain,
		oauthCfg: &oauth2.Config{
			ClientID:     clientID,
			ClientSecret: clientSecret,
			RedirectURL:  redirectURL,
			Endpoint:     githuboauth.Endpoint,
			// public_repo covers Flow A reviews + Flow B fork-mode on any public repo.
			Scopes: []string{"read:user", "public_repo"},
		},
	}
}

// Login redirects to GitHub's OAuth consent screen with a CSRF state cookie.
func (h *AuthHandler) Login(w http.ResponseWriter, r *http.Request) {
	state := randToken()
	http.SetCookie(w, &http.Cookie{
		Name: oauthStateCookie, Value: state, Path: "/",
		HttpOnly: true, Secure: h.CookieSecure, SameSite: http.SameSiteLaxMode,
		MaxAge: 600, Domain: h.CookieDomain,
	})
	http.Redirect(w, r, h.oauthCfg.AuthCodeURL(state), http.StatusFound)
}

// Callback exchanges the code, fetches the user, upserts them with an encrypted
// OAuth token, and sets the session JWT cookie.
func (h *AuthHandler) Callback(w http.ResponseWriter, r *http.Request) {
	stateCookie, err := r.Cookie(oauthStateCookie)
	if err != nil || stateCookie.Value == "" || stateCookie.Value != r.URL.Query().Get("state") {
		respond.Error(w, r, http.StatusBadRequest, "OAUTH_STATE_MISMATCH", "invalid oauth state")
		return
	}
	code := r.URL.Query().Get("code")
	if code == "" {
		respond.Error(w, r, http.StatusBadRequest, "OAUTH_NO_CODE", "missing oauth code")
		return
	}

	tok, err := h.oauthCfg.Exchange(r.Context(), code)
	if err != nil {
		h.Log.Error("oauth exchange failed", "err", err)
		respond.Error(w, r, http.StatusBadGateway, "OAUTH_EXCHANGE_FAILED", "could not exchange code")
		return
	}

	gh := github.NewClient(h.oauthCfg.Client(r.Context(), tok))
	ghUser, _, err := gh.Users.Get(r.Context(), "")
	if err != nil {
		h.Log.Error("github user fetch failed", "err", err)
		respond.Error(w, r, http.StatusBadGateway, "GITHUB_USER_FETCH_FAILED", "could not fetch user")
		return
	}

	enc, err := h.Crypto.Encrypt([]byte(tok.AccessToken))
	if err != nil {
		respond.Error(w, r, http.StatusInternalServerError, "ENCRYPT_FAILED", "could not encrypt token")
		return
	}

	user, err := h.Q.UpsertUser(r.Context(), store.UpsertUserParams{
		GithubID:                  ghUser.GetID(),
		GithubLogin:               ghUser.GetLogin(),
		GithubOauthTokenEncrypted: enc,
	})
	if err != nil {
		h.Log.Error("upsert user failed", "err", err)
		respond.Error(w, r, http.StatusInternalServerError, "DB_ERROR", "could not persist user")
		return
	}

	jwtStr, err := h.Tokens.Issue(user.ID, user.GithubLogin, user.Uuid.String())
	if err != nil {
		respond.Error(w, r, http.StatusInternalServerError, "JWT_ISSUE_FAILED", "could not issue session")
		return
	}
	http.SetCookie(w, &http.Cookie{
		Name: gwmw.SessionCookieName, Value: jwtStr, Path: "/",
		HttpOnly: true, Secure: h.CookieSecure, SameSite: http.SameSiteLaxMode,
		Expires: time.Now().Add(h.Tokens.TTL()), Domain: h.CookieDomain,
	})
	// clear state cookie
	http.SetCookie(w, &http.Cookie{Name: oauthStateCookie, Value: "", Path: "/", MaxAge: -1})

	http.Redirect(w, r, h.WebBaseURL, http.StatusFound)
}

// Install redirects to the GitHub App installation page.
func (h *AuthHandler) Install(w http.ResponseWriter, r *http.Request) {
	if h.InstallURL == "" {
		respond.Error(w, r, http.StatusNotImplemented, "INSTALL_URL_UNSET", "GITHUB_APP_INSTALL_URL not configured")
		return
	}
	http.Redirect(w, r, h.InstallURL, http.StatusFound)
}

// Me returns the current authenticated user.
func (h *AuthHandler) Me(w http.ResponseWriter, r *http.Request) {
	claims, ok := gwmw.ClaimsFromContext(r.Context())
	if !ok {
		respond.Error(w, r, http.StatusUnauthorized, "UNAUTHENTICATED", "no session")
		return
	}
	user, err := h.Q.GetUserByID(r.Context(), claims.UserID)
	if err != nil {
		respond.Error(w, r, http.StatusNotFound, "USER_NOT_FOUND", "user not found")
		return
	}
	respond.OK(w, r, apitypes.User{
		UUID:        user.Uuid.String(),
		GithubID:    user.GithubID,
		GithubLogin: user.GithubLogin,
		AvatarURL:   fmt.Sprintf("https://avatars.githubusercontent.com/u/%d?v=4", user.GithubID),
	})
}

// Logout clears the session cookie.
func (h *AuthHandler) Logout(w http.ResponseWriter, r *http.Request) {
	http.SetCookie(w, &http.Cookie{
		Name: gwmw.SessionCookieName, Value: "", Path: "/",
		HttpOnly: true, Secure: h.CookieSecure, SameSite: http.SameSiteLaxMode,
		MaxAge: -1, Domain: h.CookieDomain,
	})
	respond.OK(w, r, map[string]bool{"ok": true})
}

func randToken() string {
	b := make([]byte, 24)
	_, _ = rand.Read(b)
	return base64.RawURLEncoding.EncodeToString(b)
}
