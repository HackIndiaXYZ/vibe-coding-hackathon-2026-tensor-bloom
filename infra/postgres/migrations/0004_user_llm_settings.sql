-- Per-user LLM routing + bring-your-own provider API keys (UI-configurable).
-- Overrides the operator config/llm-routing.yaml at goal time, per user.
CREATE TABLE IF NOT EXISTS user_llm_settings (
    user_id      BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    routing_json JSONB NOT NULL DEFAULT '{}',   -- { "<role|tool>": {"provider":..,"model":..} }
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_provider_keys (
    user_id           BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider          TEXT NOT NULL,            -- anthropic | openai | groq | ...
    api_key_encrypted BYTEA NOT NULL,           -- AES-GCM at rest (identity.Crypto)
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, provider)
);
