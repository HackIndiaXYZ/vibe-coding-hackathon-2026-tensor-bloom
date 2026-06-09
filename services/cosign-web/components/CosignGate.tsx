"use client";

import { useEffect, useState } from "react";
import type { CriticIteration, Interrupt, ResumeRequest, ReviewDraft } from "@/lib/types";
import { ReviewEditor } from "./ReviewEditor";
import { TranscriptViewer } from "./TranscriptViewer";
import { DiffViewer } from "./DiffViewer";
import { SignatureStamp } from "./blueprint/SignatureStamp";

// The cosign gesture (PRD §1.2.1 — "the gate is the product"). a = cosign, r = revise, x = reject.
export function CosignGate({
  interrupt,
  transcript,
  onResolve,
  mock = false,
}: {
  interrupt: Interrupt;
  transcript: CriticIteration[];
  onResolve: (req: ResumeRequest) => Promise<void>;
  mock?: boolean;
}) {
  const isReview = interrupt.type === "pr_review_gate";
  const [edited, setEdited] = useState<ReviewDraft>(interrupt.payload as unknown as ReviewDraft);
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState(false);

  async function resolve(decision: ResumeRequest["decision"]) {
    setBusy(true);
    try {
      await onResolve({
        decision,
        feedback: feedback || undefined,
        edited_review: isReview && decision === "approve" ? edited : undefined,
      });
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.target as HTMLElement)?.tagName?.match(/INPUT|TEXTAREA/)) return;
      if (e.key === "a") resolve("approve");
      else if (e.key === "x") resolve("reject");
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [edited, feedback]);

  const finalDiff = (interrupt.payload?.final_diff as string) ?? "";

  return (
    <div
      className="panel ticks rise"
      style={{ borderColor: "var(--cyan-dim)", boxShadow: "0 0 40px rgba(52,226,226,0.10)" }}
    >
      <span className="tick-bl" /><span className="tick-br" />
      <div className="flex items-center justify-between border-b border-[var(--cyan-dim)] px-4 py-3">
        <div className="flex items-center gap-3">
          <SignatureStamp />
          <h2 className="text-base">{isReview ? "cosign this review" : "cosign & open PR"}</h2>
        </div>
        <span className="label">posted as you · not a bot</span>
      </div>

      <div className="p-4">
        {isReview ? (
          <ReviewEditor initial={edited} onChange={setEdited} />
        ) : (
          <div className="space-y-3">
            <TranscriptViewer rounds={transcript} />
            <div>
              <span className="label">
                final diff
                {mock && (
                  <span className="ml-2" style={{ color: "var(--warn)" }}>
                    · synthetic (mock — not your repo)
                  </span>
                )}
              </span>
              <div className="mt-1">
                <DiffViewer diff={finalDiff} />
              </div>
            </div>
          </div>
        )}

        <textarea
          className="field mt-4 resize-y"
          rows={2}
          placeholder="revision feedback (optional, used with Revise)…"
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
        />

        <div className="mt-3 flex flex-wrap gap-2">
          <button disabled={busy} onClick={() => resolve("approve")} className="btn btn-primary">
            ◇ cosign <kbd className="ml-1">a</kbd>
          </button>
          <button disabled={busy} onClick={() => resolve("revise")} className="btn">
            revise <kbd className="ml-1">r</kbd>
          </button>
          <button
            disabled={busy}
            onClick={() => resolve("reject")}
            className="btn"
            style={{ color: "var(--danger)", borderColor: "rgba(248,113,113,0.3)" }}
          >
            reject <kbd className="ml-1">x</kbd>
          </button>
        </div>
      </div>
    </div>
  );
}
