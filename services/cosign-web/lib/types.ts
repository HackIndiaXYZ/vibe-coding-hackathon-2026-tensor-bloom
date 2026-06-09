// Wire contract — mirror of cosign-api pkg/apitypes (ARCHITECTURE §8).
export interface Envelope<T = unknown> {
  data: T;
  meta: { request_id: string; timestamp: string };
  error: { code: string; message: string } | null;
}

export interface User {
  uuid: string;
  github_id: number;
  github_login: string;
  avatar_url: string;
}

export type GoalType = "pr_review" | "issue_implement" | "manual";

export interface CreateGoalRequest {
  type: GoalType;
  pr_url?: string;
  issue_url?: string;
  steer?: string;
}

export interface GoalSummary {
  uuid: string;
  type: GoalType;
  title: string;
  status: string;
  repo_full_name: string;
  github_pr_number?: number;
  github_issue_number?: number;
  fork_mode: boolean;
  created_at: string;
  completed_at?: string;
}

export interface PerFileComment {
  path: string;
  line?: number;
  comment: string;
}

export interface ReviewDraft {
  summary: string;
  risk_score: number;
  per_file_comments: PerFileComment[];
  ask_changes: string[];
  praise: string[];
}

export interface CriticIteration {
  round_number: number;
  implementer_diff: string;
  self_satisfaction?: number;
  critic_feedback?: Record<string, unknown>;
}

export interface CostRow {
  agent_role: string;
  call_count: number;
  tokens_in: number;
  tokens_out: number;
  cached_tokens: number;
  cost_usd: number;
}

export interface Interrupt {
  uuid: string;
  type: "pr_review_gate" | "critic_loop_gate" | "dangerous_code" | "steer";
  payload: Record<string, unknown>;
  decision?: string;
  resolved_at?: string;
}

export interface GoalDetail extends GoalSummary {
  description: string;
  interrupts: Interrupt[];
  transcript: CriticIteration[];
  cost_breakdown: CostRow[];
  output_url?: string;
}

export interface ResumeRequest {
  decision: "approve" | "revise" | "reject";
  feedback?: string;
  edited_review?: ReviewDraft;
}

// ── LLM settings (per-user routing + BYO keys) ────────────────────────────────
export interface RouteChoice {
  provider: string;
  model: string;
}
export interface ProviderStatus {
  name: string;
  has_key: boolean;
}
export interface RoleSlot {
  key: string;
  label: string;
  deterministic: boolean;
  operator_model: string;
}
export interface ProviderModels {
  provider: string;
  models: string[];
}
export interface SettingsResponse {
  routing: Record<string, RouteChoice>;
  providers: ProviderStatus[];
  catalog: ProviderModels[];
  roles: RoleSlot[];
}

export type SSEEventType =
  | "run.started"
  | "goal.status_changed"
  | "task.started"
  | "task.tool_call"
  | "task.tool_result"
  | "task.completed"
  | "task.failed"
  | "node.started"
  | "node.completed"
  | "iteration.implementer"
  | "iteration.critic"
  | "gate.pending"
  | "gate.resolved"
  | "goal.completed"
  | "goal.failed"
  | "goal.cancelled";

export interface SSEEvent {
  id: string;
  event: SSEEventType | string;
  data: Record<string, unknown>;
}
