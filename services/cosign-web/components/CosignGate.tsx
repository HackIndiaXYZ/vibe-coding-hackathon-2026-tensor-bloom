"use client";

import { useEffect, useState } from "react";
import type { CriticIteration, Interrupt, ResumeRequest, ReviewDraft } from "@/lib/types";
import { ReviewEditor } from "./ReviewEditor";
import { TranscriptViewer } from "./TranscriptViewer";
import { DiffViewer } from "./DiffViewer";

// The cosign gesture. Renders the artifact the human reviews, then resolves the
// gate. Keyboard: a = cosign, r = revise, x = reject.
export function CosignGate({
  interrupt,
  transcript,
  onResolve,
}: {
  interrupt: Interrupt;
  transcript: CriticIteration[];
  onResolve: (req: ResumeRequest) => Promise<void>;
}) {
  const isReview = interrupt.type === "pr_review_gate";
  const [edited, setEdited] = useState<ReviewDraft>(
    interrupt.payload as unknown as ReviewDraft,
  );
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
    <div className="rounded-lg border-2 border-black p-4 dark:border-white">
      <div className="mb-3 flex items-center gap-2">
        <span className="text-lg">✋</span>
        <h2 className="text-lg font-semibold">
          {isReview ? "Cosign this review" : "Cosign & open PR"}
        </h2>
        <span className="ml-auto text-xs text-neutral-500">
          posted as you · not a bot
        </span>
      </div>

      {isReview ? (
        <ReviewEditor initial={edited} onChange={setEdited} />
      ) : (
        <div className="space-y-3">
          <TranscriptViewer rounds={transcript} />
          <div>
            <span className="text-xs font-medium text-neutral-500">Final diff</span>
            <DiffViewer diff={finalDiff} />
          </div>
        </div>
      )}

      <textarea
        className="mt-3 w-full rounded border border-neutral-300 bg-transparent p-2 text-sm dark:border-neutral-700"
        rows={2}
        placeholder="Revision feedback (optional, used with Revise)…"
        value={feedback}
        onChange={(e) => setFeedback(e.target.value)}
      />

      <div className="mt-3 flex gap-2">
        <button
          disabled={busy}
          onClick={() => resolve("approve")}
          className="rounded bg-black px-4 py-2 text-sm font-semibold text-white disabled:opacity-50 dark:bg-white dark:text-black"
        >
          Cosign <kbd className="ml-1 opacity-60">a</kbd>
        </button>
        <button
          disabled={busy}
          onClick={() => resolve("revise")}
          className="rounded border border-neutral-300 px-4 py-2 text-sm dark:border-neutral-700"
        >
          Revise <kbd className="ml-1 opacity-60">r</kbd>
        </button>
        <button
          disabled={busy}
          onClick={() => resolve("reject")}
          className="rounded border border-red-300 px-4 py-2 text-sm text-red-600"
        >
          Reject <kbd className="ml-1 opacity-60">x</kbd>
        </button>
      </div>
    </div>
  );
}
