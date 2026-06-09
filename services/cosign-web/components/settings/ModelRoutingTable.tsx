"use client";

import type { ProviderModels, RoleSlot, RouteChoice } from "@/lib/types";

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
  const id = `models-${title.replace(/\s+/g, "-")}`;
  return (
    <div
      className="grid grid-cols-[1fr_120px_1fr] items-center gap-3 px-4 py-3"
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
          <select
            className="field"
            value={choice?.provider ?? ""}
            onChange={(e) => {
              const provider = e.target.value;
              if (!provider) return onChange(null);
              const pm = catalog.find((c) => c.provider === provider)?.models ?? [];
              const keep = choice?.model && pm.includes(choice.model) ? choice.model : (pm[0] ?? "");
              onChange({ provider, model: keep });
            }}
          >
            <option value="">default</option>
            {providers.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
          <div className="flex items-center gap-2">
            <input
              className="field"
              list={id}
              placeholder={choice?.provider ? "model id" : placeholder}
              disabled={!choice?.provider}
              value={choice?.model ?? ""}
              onChange={(e) => onChange({ provider: choice?.provider ?? "", model: e.target.value })}
            />
            <datalist id={id}>{models.map((m) => <option key={m} value={m} />)}</datalist>
          </div>
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
