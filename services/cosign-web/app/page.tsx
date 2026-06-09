"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { GoalSummary, User } from "@/lib/types";

export default function Dashboard() {
  const [user, setUser] = useState<User | null>(null);
  const [goals, setGoals] = useState<GoalSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .me()
      .then((u) => {
        setUser(u);
        return api.listGoals();
      })
      .then(setGoals)
      .catch((e) => {
        if (!(e instanceof ApiError)) console.error(e);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Skeleton />;

  if (!user) {
    return (
      <div className="py-16 text-center">
        <h1 className="text-2xl font-semibold">AI drafts the work. You cosign.</h1>
        <p className="mt-2 text-neutral-500">
          Reviews and PRs shipped under your name — never a bot&apos;s.
        </p>
        <a
          href={api.loginUrl()}
          className="mt-6 inline-block rounded bg-black px-4 py-2 text-white dark:bg-white dark:text-black"
        >
          Sign in with GitHub
        </a>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex gap-3">
        <Link href="/review" className="rounded border border-neutral-300 px-4 py-2 text-sm dark:border-neutral-700">
          Review a PR
        </Link>
        <Link href="/resolve" className="rounded border border-neutral-300 px-4 py-2 text-sm dark:border-neutral-700">
          Resolve an issue
        </Link>
      </div>

      <section>
        <h2 className="mb-2 text-sm font-medium text-neutral-500">Recent goals</h2>
        {goals.length === 0 ? (
          <p className="text-sm text-neutral-500">No goals yet. Start one above.</p>
        ) : (
          <ul className="divide-y divide-neutral-200 dark:divide-neutral-800">
            {goals.map((g) => (
              <li key={g.uuid}>
                <Link href={`/goals/${g.uuid}`} className="flex items-center gap-3 py-2 hover:opacity-80">
                  <StatusDot status={g.status} />
                  <span className="text-sm">{g.title}</span>
                  <span className="ml-auto text-xs text-neutral-500">{g.status}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function StatusDot({ status }: { status: string }) {
  const color =
    status === "done" ? "bg-emerald-500"
      : status === "awaiting_human" ? "bg-amber-500"
      : status === "failed" || status === "cancelled" ? "bg-red-500"
      : "bg-blue-500";
  return <span className={`h-2 w-2 rounded-full ${color}`} />;
}

function Skeleton() {
  return <div className="h-32 animate-pulse rounded bg-neutral-100 dark:bg-neutral-900" />;
}
