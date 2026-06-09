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

  if (loading) {
    return <div className="panel ticks h-40 pulse" />;
  }

  if (!user) {
    return (
      <div className="rise mx-auto mt-10 max-w-xl">
        <div className="label kicker mb-3">{"// cosign — human-in-the-loop dev agent"}</div>
        <h1 className="mb-4 text-3xl leading-tight">
          AI drafts the work. An AI critic refines it.{" "}
          <span className="text-[var(--cyan)]">You cosign.</span>
        </h1>
        <p className="mb-6 text-sm text-[var(--text-dim)]">
          Reviews and pull requests ship under your name on GitHub — never a bot&apos;s.
          You enter once, at the end, to sign.
        </p>
        <a href={api.loginUrl()} className="btn btn-primary">
          sign in with github →
        </a>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <section className="rise">
        <div className="label kicker mb-2">{"// start a goal"}</div>
        <div className="grid gap-3 sm:grid-cols-2">
          <CTA href="/review" k="A" title="Review a PR" sub="reviewer agent drafts · you edit + cosign · posts as you" />
          <CTA href="/resolve" k="B" title="Resolve an issue" sub="implementer ⇄ critic loop · cosign the transcript · PR as you" />
        </div>
      </section>

      <section className="rise" style={{ animationDelay: "80ms" }}>
        <div className="mb-2 flex items-baseline justify-between">
          <div className="label kicker">{"// recent goals"}</div>
          <div className="label">{goals.length} total</div>
        </div>
        <div className="panel ticks">
          <span className="tick-bl" /><span className="tick-br" />
          {goals.length === 0 ? (
            <div className="p-6 text-sm text-[var(--text-dim)]">No goals yet — start one above.</div>
          ) : (
            <ul>
              {goals.map((g, i) => (
                <li key={g.uuid} className={i > 0 ? "border-t border-[var(--line)]" : ""}>
                  <Link
                    href={`/goals/${g.uuid}`}
                    className="group flex items-center gap-3 px-4 py-3 transition-colors hover:bg-[var(--panel-2)]"
                  >
                    <StatusGlyph status={g.status} />
                    <span className="mono text-xs text-[var(--text-dim)]">
                      {g.type === "pr_review" ? "A" : "B"}
                    </span>
                    <span className="flex-1 truncate text-sm group-hover:text-[var(--cyan)]">{g.title}</span>
                    <span className="label">{g.status.replace("_", " ")}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </div>
  );
}

function CTA({ href, k, title, sub }: { href: string; k: string; title: string; sub: string }) {
  return (
    <Link href={href} className="panel ticks group block p-4 transition-colors hover:bg-[var(--panel-2)]">
      <span className="tick-bl" /><span className="tick-br" />
      <div className="flex items-center gap-2">
        <span className="mono text-xs text-[var(--cyan)]">flow·{k.toLowerCase()}</span>
      </div>
      <div className="mt-1 text-lg group-hover:text-[var(--cyan)]">{title}</div>
      <div className="mt-1 text-xs text-[var(--text-dim)]">{sub}</div>
    </Link>
  );
}

function StatusGlyph({ status }: { status: string }) {
  const map: Record<string, [string, string]> = {
    done: ["✓", "var(--ok)"],
    awaiting_human: ["✋", "var(--warn)"],
    executing: ["⟳", "var(--cyan)"],
    planning: ["⟳", "var(--cyan)"],
    pending: ["·", "var(--text-dim)"],
    failed: ["✗", "var(--danger)"],
    cancelled: ["⊘", "var(--danger)"],
  };
  const [glyph, color] = map[status] ?? ["·", "var(--text-dim)"];
  const spin = status === "executing" || status === "planning";
  return (
    <span className={`mono w-4 text-center ${spin ? "pulse" : ""}`} style={{ color }}>
      {glyph}
    </span>
  );
}
