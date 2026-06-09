-- Store the target repo's full name directly on the goal so the hot path needs
-- neither a repositories row nor a GitHub API call. The repositories table stays
-- for App installations / webhooks (deferred).
ALTER TABLE goals ADD COLUMN IF NOT EXISTS repo_full_name TEXT;
