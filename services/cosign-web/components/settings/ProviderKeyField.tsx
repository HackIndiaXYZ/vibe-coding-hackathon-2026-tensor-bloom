"use client";

import { useState } from "react";

// A masked BYO API-key field. Never shows the stored key — only "key set ✓".
// `hasKey` is server truth (the page re-fetches settings after every save).
export function ProviderKeyField({
  provider,
  hasKey,
  onSave,
}: {
  provider: string;
  hasKey: boolean;
  onSave: (provider: string, key: string) => Promise<void>;
}) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(key: string) {
    setBusy(true);
    try {
      await onSave(provider, key);
      setValue("");
    } catch {
      /* page surfaces the error toast */
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-3 border-t border-[var(--line)] px-4 py-3 first:border-t-0">
      <span className="mono w-24 text-sm text-[var(--text)]">{provider}</span>
      <input
        type="password"
        autoComplete="off"
        placeholder={hasKey ? "•••••••••• (stored)" : "paste api key"}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        className="field flex-1"
      />
      {hasKey && value === "" ? (
        <>
          <span className="mono text-xs" style={{ color: "var(--ok)" }}>key set ✓</span>
          <button disabled={busy} onClick={() => save("")} className="btn" style={{ color: "var(--danger)" }}>
            clear
          </button>
        </>
      ) : (
        <button disabled={busy || value === ""} onClick={() => save(value)} className="btn btn-primary">
          {busy ? "…" : "save"}
        </button>
      )}
    </div>
  );
}
