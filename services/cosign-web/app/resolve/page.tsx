"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";

export default function ResolvePage() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [steer, setSteer] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const { uuid } = await api.createGoal({ type: "issue_implement", issue_url: url, steer });
      router.push(`/goals/${uuid}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "failed");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto max-w-xl space-y-4">
      <h1 className="text-xl font-semibold">Resolve an issue with Cosign</h1>
      <p className="text-sm text-neutral-500">
        Paste a GitHub issue URL. An implementer and a critic iterate to convergence; you cosign
        the transcript once, and the PR opens authored by you.
      </p>
      <input
        required
        type="url"
        placeholder="https://github.com/owner/repo/issues/123"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        className="w-full rounded border border-neutral-300 bg-transparent p-2 text-sm dark:border-neutral-700"
      />
      <textarea
        placeholder="Optional steering note (e.g. also update tests under tests/foo/)"
        value={steer}
        onChange={(e) => setSteer(e.target.value)}
        rows={3}
        className="w-full rounded border border-neutral-300 bg-transparent p-2 text-sm dark:border-neutral-700"
      />
      {err && <p className="text-sm text-red-600">{err}</p>}
      <button
        disabled={busy}
        className="rounded bg-black px-4 py-2 text-sm font-semibold text-white disabled:opacity-50 dark:bg-white dark:text-black"
      >
        {busy ? "Starting…" : "Resolve with Cosign"}
      </button>
    </form>
  );
}
