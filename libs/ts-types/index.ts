// Wire contract consumed by cosign-web. Mirror of cosign-api's pkg/apitypes
// (ARCHITECTURE §8). Keep field-for-field in sync with apitypes.go.

export interface Envelope<T = unknown> {
  data: T;
  meta: Meta;
  error: APIError | null;
}

export interface Meta {
  request_id: string;
  timestamp: string;
}

export interface APIError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

// ── Auth ──────────────────────────────────────────────────────────────────────
export interface User {
  uuid: string;
  github_id: number;
  github_login: string;
  avatar_url: string;
}

// ── Goals ─────────────────────────────────────────────────────────────────────
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

export interface GoalDetail extends GoalSummary {
  description: string;
  interrupts: Interrupt[];
  transcript: CriticIteration[];
  cost_breakdown: CostRow[];
  output_url?: string;
}

export interface Interrupt {
  uuid: string;
  type: "pr_review_gate" | "critic_loop_gate" | "dangerous_code" | "steer";
  payload: Record<string, unknown>;
  decision?: string;
  resolved_at?: string;
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

// ── Resume (cosign / revise / reject) ─────────────────────────────────────────
export interface ResumeRequest {
  decision: "approve" | "revise" | "reject";
  feedback?: string;
  edited_review?: ReviewDraft;
}

export interface ReviewDraft {
  summary: string;
  risk_score: number;
  per_file_comments: PerFileComment[];
  ask_changes: string[];
  praise: string[];
}

export interface PerFileComment {
  path: string;
  line?: number;
  comment: string;
}

// ── SSE event types (ARCHITECTURE §8.3) ───────────────────────────────────────
export type SSEEventType =
  | "goal.status_changed"
  | "task.started"
  | "task.tool_call"
  | "task.completed"
  | "task.failed"
  | "iteration.implementer"
  | "iteration.critic"
  | "gate.pending"
  | "gate.resolved"
  | "goal.completed"
  | "goal.failed"
  | "goal.cancelled"
  | "cost.updated";
