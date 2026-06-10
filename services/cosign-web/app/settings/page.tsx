"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { RouteChoice, SettingsResponse } from "@/lib/types";
import { Panel } from "@/components/blueprint/Panel";
import { BudgetBanner } from "@/components/blueprint/Banner";
import { ToastHost, useToast } from "@/components/blueprint/Toast";
import { ModelRoutingTable } from "@/components/settings/ModelRoutingTable";
import { ProviderKeyField } from "@/components/settings/ProviderKeyField";

export default function SettingsPage() {
  const [data, setData] = useState<SettingsResponse | null>(null);
  const [routing, setRouting] = useState<Record<string, RouteChoice>>({});
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const { toasts, push } = useToast();

  useEffect(() => {
    api.getSettings().then((s) => {
      setData(s);
      setRouting(s.routing ?? {});
    }).catch((e) => push(e?.message ?? "failed to load settings", "error"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!data) return <div className="panel ticks h-40 pulse" />;

  const connected = data.providers.filter((p) => p.has_key);

  function setChoice(key: string, choice: RouteChoice | null) {
    setDirty(true);
    setRouting((prev) => {
      const next = { ...prev };
      if (choice) next[key] = choice;
      else delete next[key];
      return next;
    });
  }

  async function saveRouting() {
    setBusy(true);
    try {
      const clean: Record<string, RouteChoice> = {};
      for (const [k, v] of Object.entries(routing)) {
        if (v.provider && v.model) clean[k] = v;
      }
      await api.putRouting(clean);
      // server-confirm: re-read what was actually stored
      const s = await api.getSettings();
      setData(s);
      setRouting(s.routing ?? {});
      setDirty(false);
      push(`routing saved · ${Object.keys(s.routing ?? {}).length} override(s)`);
    } catch (e) {
      push(e instanceof Error ? e.message : "save failed", "error");
    } finally {
      setBusy(false);
    }
  }

  async function saveKey(provider: string, key: string) {
    try {
      await api.putProviderKey(provider, key);
      const s = await api.getSettings();
      setData(s);
      push(key ? `${provider} key saved` : `${provider} key removed`);
    } catch (e) {
      push(e instanceof Error ? e.message : "key save failed", "error");
      throw e;
    }
  }

  const overrideCount = Object.values(routing).filter((v) => v.provider && v.model).length;

  return (
    <div className="space-y-6">
      <ToastHost toasts={toasts} />

      <div className="rise">
        <div className="label kicker mb-1">{"// settings"}</div>
        <h1 className="text-xl">Model routing &amp; keys</h1>
        <p className="mt-1 text-sm text-[var(--text-dim)]">
          Set one <span className="mono text-[var(--text)]">Default · all roles</span> model and it&apos;s
          used everywhere — or override individual roles below. Bring your own provider keys (encrypted at
          rest, never returned to your browser). Anything still unset falls back to the operator config.
        </p>
      </div>

      <div className="rise" style={{ animationDelay: "20ms" }}>
        <BudgetBanner
          sharedKeyAvailable={data.shared_key_available}
          usingOwnKey={data.using_own_key}
          usageUsd={data.usage_usd}
          capUsd={data.cap_usd}
          defaultModel={data.default_model}
        />
      </div>

      <div className="rise" style={{ animationDelay: "40ms" }}>
        <Panel title="connected providers" right={`${connected.length}/${data.providers.length} keyed`}>
          {connected.length === 0 ? (
            <p className="mono text-xs text-[var(--text-dim)]">
              no keys saved yet — add one below to use that provider with your own billing.
            </p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {connected.map((p) => (
                <span
                  key={p.name}
                  className="inline-flex items-center gap-2 border px-3 py-1.5 mono text-xs"
                  style={{ borderColor: "var(--ok)", color: "var(--ok)" }}
                >
                  <span>◆</span> {p.name}
                  <span className="text-[var(--text-dim)]">key set</span>
                </span>
              ))}
            </div>
          )}
        </Panel>
      </div>

      <div className="rise" style={{ animationDelay: "80ms" }}>
        <Panel title="per-role routing" right="user → operator → fallback">
          <ModelRoutingTable
            roles={data.roles}
            catalog={data.catalog}
            routing={routing}
            onChange={setChoice}
          />
          <div className="mt-3 flex items-center gap-3 border-t border-[var(--line)] pt-3">
            <button disabled={busy || !dirty} onClick={saveRouting} className="btn btn-primary">
              {busy ? "saving…" : dirty ? "save routing" : "saved ✓"}
            </button>
            <span className="label">{overrideCount} override(s)</span>
            {dirty && (
              <span className="mono text-xs" style={{ color: "var(--warn)" }}>● unsaved changes</span>
            )}
          </div>
        </Panel>
      </div>

      <div className="rise" style={{ animationDelay: "120ms" }}>
        <Panel title="provider api keys — bring your own" right="AES-GCM at rest">
          {data.providers.map((p) => (
            <ProviderKeyField key={p.name} provider={p.name} hasKey={p.has_key} onSave={saveKey} />
          ))}
        </Panel>
      </div>
    </div>
  );
}
