-- Seed the three v1 agent roles with their tool allowlists (ARCHITECTURE §6.4).
-- capability_hash is SHA-256 of the capabilities JSON (verified on each check).
INSERT INTO agents (role, display_name, capabilities, capability_hash) VALUES
  ('implementer', 'Implementer',
   '{"tools":["github_ops","github_pr","code_exec","file_ops","test_runner","lint","repo_map","diff_analysis","web_search"],"trust_level":2}',
   encode(digest('{"tools":["github_ops","github_pr","code_exec","file_ops","test_runner","lint","repo_map","diff_analysis","web_search"],"trust_level":2}', 'sha256'), 'hex')),
  ('reviewer', 'Reviewer',
   '{"tools":["github_ops","file_ops","repo_map","review","diff_analysis","lint","web_search"],"trust_level":2}',
   encode(digest('{"tools":["github_ops","file_ops","repo_map","review","diff_analysis","lint","web_search"],"trust_level":2}', 'sha256'), 'hex')),
  ('critic', 'Critic',
   '{"tools":["diff_analysis","test_runner","lint","repo_map","web_search"],"trust_level":1}',
   encode(digest('{"tools":["diff_analysis","test_runner","lint","repo_map","web_search"],"trust_level":1}', 'sha256'), 'hex'))
ON CONFLICT DO NOTHING;
