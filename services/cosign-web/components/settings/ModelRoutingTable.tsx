"use client";

import { useState } from "react";
import type { ProviderModels, RoleSlot, RouteChoice } from "@/lib/types";
import { Select } from "@/components/blueprint/Select";

const CUSTOM = "__custom__";

function RouteRow({
  title,
  sub,
  accent,
  deterministic,
  providers,
  catalog,
  choice,
  placeholder,
  onChange,
}: {
  title: string;
  sub: string;
  accent?: boolean;
  deterministic?: boolean;
  providers: string[];
  catalog: ProviderModels[];
  choice?: RouteChoice;
  placeholder?: string;
  onChange: (c: RouteChoice | null) => void;
}) {
  const models = catalog.find((c) => c.provider === choice?.provider)?.models ?? [];
  const isCustomModel = Boolean(choice?.model && !models.includes(choice.model));
  const [customOpen, setCustomOpen] = useState(isCustomModel);

  return (
    <div
      className="grid grid-cols-[1fr_140px_1fr] items-center gap-3 px-4 py-3"
      style={accent ? { background: "var(--cyan-deep)" } : undefined}
    >
      <div>
        <div className="mono text-sm" style={{ color: accent ? "var(--cyan)" : "var(--text)" }}>{title}</div>
        <div className="label">{sub}</div>
      </div>
      {deterministic ? (
        <div className="col-span-2 mono text-xs text-[var(--text-faint)]">deterministic — no model</div>
      ) : (
        <>
          <Select
            value={choice?.provider ?? ""}
            placeholder="default"
            options={[{ value: "", label: "default" }, ...providers.map((p) => ({ value: p }))]}
            onChange={(provider) => {
              if (!provider) return onChange(null);
              const pm = catalog.find((c) => c.provider === provider)?.models ?? [];
              const keep = choice?.model && pm.includes(choice.model) ? choice.model : (pm[0] ?? "");
              setCustomOpen(false);
              onChange({ provider, model: keep });
            }}
          />
          {customOpen || isCustomModel ? (
            <input
              className="field"
              autoFocus
              placeholder="custom model id"
              disabled={!choice?.provider}
              value={choice?.model ?? ""}
              onChange={(e) => onChange({ provider: choice?.provider ?? "", model: e.target.value })}
            />
          ) : (
            <Select
              value={choice?.model ?? ""}
              placeholder={choice?.provider ? "model" : placeholder}
              disabled={!choice?.provider}
              options={[...models.map((m) => ({ value: m })), { value: CUSTOM, label: "custom…" }]}
              onChange={(m) => {
                if (m === CUSTOM) {
                  setCustomOpen(true);
                  return;
                }
                onChange({ provider: choice?.provider ?? "", model: m });
              }}
            />
          )}
        </>
      )}
    </div>
  );
}

// Per-role provider+model picker, with a single "default for all roles" row on top.
export function ModelRoutingTable({
  roles,
  catalog,
  routing,
  onChange,
}: {
  roles: RoleSlot[];
  catalog: ProviderModels[];
  routing: Record<string, RouteChoice>;
  onChange: (key: string, choice: RouteChoice | null) => void;
}) {
  const providers = catalog.map((c) => c.provider);
  const def = routing["_default"];
  const defHint = def ? `→ default · ${def.provider}/${def.model}` : undefined;

  return (
    <div>
      <RouteRow
        title="Default · all roles"
        sub="used for any role left as 'default'"
        accent
        providers={providers}
        catalog={catalog}
        choice={def}
        placeholder="pick a provider"
        onChange={(c) => onChange("_default", c)}
      />
      <div className="border-t border-[var(--line)]" />
      {roles.map((role) => (
        <div key={role.key} className="border-t border-[var(--line)]">
          <RouteRow
            title={role.label}
            sub={role.key}
            deterministic={role.deterministic}
            providers={providers}
            catalog={catalog}
            choice={routing[role.key]}
            placeholder={defHint ?? `operator: ${role.operator_model}`}
            onChange={(c) => onChange(role.key, c)}
          />
        </div>
      ))}
    </div>
  );
}
