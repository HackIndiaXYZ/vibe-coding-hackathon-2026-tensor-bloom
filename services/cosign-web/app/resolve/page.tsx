"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { Panel } from "@/components/blueprint/Panel";

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
    <div className="rise mx-auto max-w-xl">
      <div className="label kicker mb-2">{"// flow·b — resolve an issue"}</div>
      <Panel title="resolve with cosign" right="impl ⇄ critic → gate">
        <p className="mb-4 text-sm text-[var(--text-dim)]">
          Paste a GitHub issue URL. An implementer and a critic iterate to convergence inside the
          sandbox; you cosign the transcript once, and the PR opens{" "}
          <span className="text-[var(--text)]">authored by you</span>.
        </p>
        <form onSubmit={submit} className="space-y-4">
          <label className="block">
            <span className="label">issue url</span>
            <input
              required
              type="url"
              placeholder="https://github.com/owner/repo/issues/123"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              className="field mt-1"
            />
          </label>
          <label className="block">
            <span className="label">steering note <span className="text-[var(--text-faint)]">— optional spec annotation</span></span>
            <textarea
              placeholder="e.g. also update the tests under tests/foo/"
              value={steer}
              onChange={(e) => setSteer(e.target.value)}
              rows={3}
              className="field mt-1 resize-y"
            />
          </label>
          {err && <p className="mono text-xs text-[var(--danger)]">! {err}</p>}
          <button disabled={busy} className="btn btn-primary">
            {busy ? "starting…" : "resolve with cosign →"}
          </button>
        </form>
      </Panel>
    </div>
  );
}
