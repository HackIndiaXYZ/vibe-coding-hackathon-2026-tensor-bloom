"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { Panel } from "@/components/blueprint/Panel";

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
    <div className="rise mx-auto max-w-xl">
      <div className="label kicker mb-2">{"// flow·a — review a pull request"}</div>
      <Panel title="review with cosign" right="reviewer → gate">
        <p className="mb-4 text-sm text-[var(--text-dim)]">
          Paste any GitHub PR URL. The reviewer agent drafts a structured review; you edit it
          to your voice and cosign — it posts on the PR <span className="text-[var(--text)]">as you</span>.
        </p>
        <form onSubmit={submit} className="space-y-4">
          <label className="block">
            <span className="label">pr url</span>
            <input
              required
              type="url"
              placeholder="https://github.com/owner/repo/pull/123"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              className="field mt-1"
            />
          </label>
          {err && <p className="mono text-xs text-[var(--danger)]">! {err}</p>}
          <button disabled={busy} className="btn btn-primary">
            {busy ? "starting…" : "review with cosign →"}
          </button>
        </form>
      </Panel>
    </div>
  );
}
