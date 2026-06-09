"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";

export default function ReviewPage() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const { uuid } = await api.createGoal({ type: "pr_review", pr_url: url });
      router.push(`/goals/${uuid}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "failed");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto max-w-xl space-y-4">
      <h1 className="text-xl font-semibold">Review a PR with Cosign</h1>
      <p className="text-sm text-neutral-500">
        Paste any GitHub PR URL. Cosign drafts a review; you edit and cosign; it posts as you.
      </p>
      <input
        required
        type="url"
        placeholder="https://github.com/owner/repo/pull/123"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        className="w-full rounded border border-neutral-300 bg-transparent p-2 text-sm dark:border-neutral-700"
      />
      {err && <p className="text-sm text-red-600">{err}</p>}
      <button
        disabled={busy}
        className="rounded bg-black px-4 py-2 text-sm font-semibold text-white disabled:opacity-50 dark:bg-white dark:text-black"
      >
        {busy ? "Starting…" : "Review with Cosign"}
      </button>
    </form>
  );
}
