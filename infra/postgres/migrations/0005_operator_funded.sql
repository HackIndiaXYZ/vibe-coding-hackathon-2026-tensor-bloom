-- Track which LLM spend was on the operator's SHARED key (vs a user's BYO key),
-- so the per-user demo budget cap only counts shared-key usage.
ALTER TABLE messages ADD COLUMN IF NOT EXISTS operator_funded BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_messages_operator_funded
    ON messages(operator_funded) WHERE operator_funded;
