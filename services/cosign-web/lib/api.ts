// Typed client for cosign-api. Unwraps the { data, meta, error } envelope and
// always sends the session cookie (credentials: include).
import type {
  CreateGoalRequest,
  Envelope,
  GoalDetail,
  GoalSummary,
  ResumeRequest,
  User,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8080";

export class ApiError extends Error {
  constructor(public code: string, message: string) {
    super(message);
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  const body = (await res.json()) as Envelope<T>;
  if (!res.ok || body.error) {
    throw new ApiError(body.error?.code ?? "ERROR", body.error?.message ?? res.statusText);
  }
  return body.data;
}

export const api = {
  me: () => req<User>("/auth/me"),
  loginUrl: () => `${API_BASE}/auth/github/login`,
  logout: () => req<{ ok: boolean }>("/auth/logout", { method: "POST" }),

  listGoals: () => req<GoalSummary[]>("/goals"),
  getGoal: (uuid: string) => req<GoalDetail>(`/goals/${uuid}`),
  createGoal: (body: CreateGoalRequest) =>
    req<{ uuid: string }>("/goals", { method: "POST", body: JSON.stringify(body) }),
  resume: (uuid: string, body: ResumeRequest) =>
    req<{ ok: boolean }>(`/goals/${uuid}/resume`, { method: "POST", body: JSON.stringify(body) }),
  cancel: (uuid: string) => req<{ ok: boolean }>(`/goals/${uuid}`, { method: "DELETE" }),
};

export const streamUrl = (uuid: string) => `${API_BASE}/stream/goals/${uuid}`;
