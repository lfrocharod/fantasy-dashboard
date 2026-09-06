"use client";

import { useEffect, useState } from "react";

interface Cfg {
  leagueId: string;
  leagueCode: string;
  entryId: string;
  currentMatchday: string;
  deadlineIso: string;
  authState: string;
  tokenSavedAt: string | null;
  hasToken: boolean;
  modelParams: string;
}

export default function SettingsPage() {
  const [cfg, setCfg] = useState<Cfg | null>(null);
  const [leagueCode, setLeagueCode] = useState("");
  const [entryId, setEntryId] = useState("");
  const [currentMatchday, setCurrentMatchday] = useState("");
  const [uefaToken, setUefaToken] = useState("");
  const [modelParams, setModelParams] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch("/api/settings")
      .then((r) => r.json())
      .then((d: Cfg) => {
        setCfg(d);
        setLeagueCode(d.leagueCode);
        setEntryId(d.entryId);
        setCurrentMatchday(d.currentMatchday);
        setModelParams(d.modelParams);
      });
  }, []);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    const body: Record<string, unknown> = { leagueCode, entryId, modelParams };
    if (currentMatchday) body.currentMatchday = Number(currentMatchday);
    if (uefaToken.trim()) body.uefaToken = uefaToken.trim();
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    setBusy(false);
    if (res.ok) {
      setMsg("Saved.");
      setUefaToken("");
      fetch("/api/settings").then((r) => r.json()).then(setCfg);
    } else {
      setMsg((await res.json().catch(() => ({}))).error ?? "Save failed");
    }
  }

  async function refresh() {
    setMsg(null);
    const res = await fetch("/api/ucl/refresh", { method: "POST" });
    setMsg(res.ok ? "Ingestion triggered." : (await res.json().catch(() => ({}))).error ?? "Refresh unavailable");
  }

  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="text-xl font-semibold">Settings</h1>

      <div className="card p-4 text-sm">
        <div className="font-medium">UEFA connection</div>
        <div className="mt-1 text-[var(--muted)]">
          State:{" "}
          <b
            style={{
              color:
                cfg?.authState === "authed"
                  ? "var(--good)"
                  : cfg?.authState === "public_only"
                    ? "var(--warn)"
                    : undefined,
            }}
          >
            {cfg?.authState ?? "…"}
          </b>
          {cfg?.tokenSavedAt && <> · token saved {new Date(cfg.tokenSavedAt).toLocaleString()}</>}
        </div>
        <p className="mt-2 text-[var(--muted)]">
          Players, prices, fixtures and projections load with no login. Your squad and
          the mini-league table need your session cookie: sign in at gaming.uefa.com,
          open DevTools → Network, click any request to{" "}
          <code>gaming.uefa.com/.../services/api/…</code>, and under{" "}
          <b>Request Headers</b> copy the whole <code>Cookie:</code> value into the box
          below. It expires after a while — re-paste when the state shows{" "}
          <code>public_only</code>.
        </p>
      </div>

      <form onSubmit={save} className="card space-y-4 p-4">
        <Field label="Mini-league code" hint="e.g. DEMO42 — the code you share to invite people">
          <input className="input w-full" value={leagueCode} onChange={(e) => setLeagueCode(e.target.value)} />
        </Field>
        <Field
          label="Your UEFA GUID"
          hint="the id in any /Gameplay/user/<GUID>/… request URL (or the 'guid' field in the Session/login response)"
        >
          <input className="input w-full font-mono text-xs" value={entryId} onChange={(e) => setEntryId(e.target.value)} />
        </Field>
        <Field label="Current matchday" hint="leave blank to auto-detect from fixtures">
          <input
            className="input w-32"
            inputMode="numeric"
            value={currentMatchday}
            onChange={(e) => setCurrentMatchday(e.target.value)}
          />
        </Field>
        <Field label="UEFA session cookie" hint={cfg?.hasToken ? "a cookie is stored; paste a new one to replace it" : "the full Cookie: request header value"}>
          <textarea
            className="input w-full font-mono text-xs"
            rows={3}
            value={uefaToken}
            onChange={(e) => setUefaToken(e.target.value)}
            placeholder="name1=value1; name2=value2; …"
          />
        </Field>
        <Field label="Model parameters (JSON)" hint="advanced — overrides projection weights">
          <textarea
            className="input w-full font-mono text-xs"
            rows={4}
            value={modelParams}
            onChange={(e) => setModelParams(e.target.value)}
            placeholder='{"form_weight": 0.3, "horizon": 2}'
          />
        </Field>

        <div className="flex items-center gap-3">
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? "Saving…" : "Save"}
          </button>
          <button type="button" className="btn" onClick={refresh}>
            Refresh data now
          </button>
          {msg && <span className="text-sm text-[var(--muted)]">{msg}</span>}
        </div>
      </form>
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <div className="text-sm font-medium">{label}</div>
      {hint && <div className="mb-1 text-xs text-[var(--muted)]">{hint}</div>}
      {children}
    </label>
  );
}
