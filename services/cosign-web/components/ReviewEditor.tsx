"use client";

import { useState } from "react";
import type { ReviewDraft } from "@/lib/types";

// Inline-editable Flow A review draft. You tweak wording, then cosign; the
// edited review posts on the PR AS YOU.
export function ReviewEditor({
  initial,
  onChange,
}: {
  initial: ReviewDraft;
  onChange: (d: ReviewDraft) => void;
}) {
  const [draft, setDraft] = useState<ReviewDraft>(initial);

  function update(patch: Partial<ReviewDraft>) {
    const next = { ...draft, ...patch };
    setDraft(next);
    onChange(next);
  }

  return (
    <div className="space-y-4">
      <label className="block">
        <span className="label">summary</span>
        <textarea
          className="field mt-1 resize-y"
          rows={3}
          value={draft.summary}
          onChange={(e) => update({ summary: e.target.value })}
        />
      </label>

      <div className="flex items-center gap-3">
        <span className="label">risk</span>
        <input
          type="range" min={0} max={1} step={0.05}
          value={draft.risk_score}
          onChange={(e) => update({ risk_score: Number(e.target.value) })}
          className="flex-1 accent-[var(--cyan)]"
        />
        <span className="mono text-xs tabular-nums text-[var(--cyan)]">{draft.risk_score.toFixed(2)}</span>
      </div>

      <EditableList label="requested changes" items={draft.ask_changes} onChange={(ask_changes) => update({ ask_changes })} />
      <EditableList label="praise" items={draft.praise} onChange={(praise) => update({ praise })} />

      {draft.per_file_comments.length > 0 && (
        <div>
          <span className="label">per-file comments</span>
          <ul className="mt-1 space-y-1">
            {draft.per_file_comments.map((c, i) => (
              <li key={i} className="border border-[var(--line)] bg-[var(--ink-2)] p-2">
                <code className="mono text-xs text-[var(--cyan)]">
                  {c.path}{c.line ? `:${c.line}` : ""}
                </code>
                <input
                  className="mt-1 w-full bg-transparent text-sm outline-none"
                  value={c.comment}
                  onChange={(e) => {
                    const next = [...draft.per_file_comments];
                    next[i] = { ...c, comment: e.target.value };
                    update({ per_file_comments: next });
                  }}
                />
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function EditableList({
  label,
  items,
  onChange,
}: {
  label: string;
  items: string[];
  onChange: (items: string[]) => void;
}) {
  return (
    <div>
      <span className="label">{label}</span>
      <div className="mt-1 space-y-1">
        {items.map((it, i) => (
          <input
            key={i}
            className="field"
            value={it}
            onChange={(e) => {
              const next = [...items];
              next[i] = e.target.value;
              onChange(next);
            }}
          />
        ))}
        <button type="button" className="label hover:text-[var(--cyan)]" onClick={() => onChange([...items, ""])}>
          + add
        </button>
      </div>
    </div>
  );
}
