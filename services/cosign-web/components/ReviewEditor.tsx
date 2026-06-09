"use client";

import { useState } from "react";
import type { ReviewDraft } from "@/lib/types";

// Inline-editable Flow A review draft. The user tweaks wording, then cosigns;
// the (edited) review posts on the PR AS THE USER.
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
    <div className="space-y-3">
      <label className="block">
        <span className="text-xs font-medium text-neutral-500">Summary</span>
        <textarea
          className="mt-1 w-full rounded border border-neutral-300 bg-transparent p-2 text-sm dark:border-neutral-700"
          rows={3}
          value={draft.summary}
          onChange={(e) => update({ summary: e.target.value })}
        />
      </label>

      <div className="flex items-center gap-2 text-sm">
        <span className="text-xs font-medium text-neutral-500">Risk</span>
        <input
          type="range" min={0} max={1} step={0.05}
          value={draft.risk_score}
          onChange={(e) => update({ risk_score: Number(e.target.value) })}
        />
        <span className="tabular-nums">{draft.risk_score.toFixed(2)}</span>
      </div>

      <EditableList
        label="Requested changes"
        items={draft.ask_changes}
        onChange={(ask_changes) => update({ ask_changes })}
      />
      <EditableList
        label="Praise"
        items={draft.praise}
        onChange={(praise) => update({ praise })}
      />

      {draft.per_file_comments.length > 0 && (
        <div>
          <span className="text-xs font-medium text-neutral-500">Per-file comments</span>
          <ul className="mt-1 space-y-1 text-sm">
            {draft.per_file_comments.map((c, i) => (
              <li key={i} className="rounded bg-neutral-100 p-2 dark:bg-neutral-800">
                <code className="text-xs text-neutral-500">
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
      <span className="text-xs font-medium text-neutral-500">{label}</span>
      <div className="mt-1 space-y-1">
        {items.map((it, i) => (
          <input
            key={i}
            className="w-full rounded border border-neutral-300 bg-transparent p-1.5 text-sm dark:border-neutral-700"
            value={it}
            onChange={(e) => {
              const next = [...items];
              next[i] = e.target.value;
              onChange(next);
            }}
          />
        ))}
        <button
          type="button"
          className="text-xs text-neutral-500 hover:underline"
          onClick={() => onChange([...items, ""])}
        >
          + add
        </button>
      </div>
    </div>
  );
}
