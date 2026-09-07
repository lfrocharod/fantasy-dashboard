"use client";

import { useEffect, useState } from "react";

export function FplSetup({ onSaved }: { onSaved: () => void }) {
  const [f, setF] = useState({ leagueId: "", entryId: "", plProfile: "" });
  const [hasCookie, setHasCookie] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/draft/config?sport=fpl")
      .then((r) => r.json())
      .then((d) => {
        setF((s) => ({ ...s, leagueId: d.leagueId || "", entryId: d.entryId || "" }));
        setHasCookie(Boolean(d.hasCookies));
      });
  }, []);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    const body: Record<string, unknown> = { sport: "fpl" };
    if (f.leagueId.trim()) body.leagueId = f.leagueId.trim();
    if (f.entryId.trim()) body.entryId = f.entryId.trim();
    if (f.plProfile.trim()) body.plProfile = f.plProfile.trim();
    const r = await fetch("/api/draft/config", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    setMsg(r.ok ? "Saved. Run ./draft.sh --sport fpl --sync to apply." : "Save failed");
    if (r.ok) {
      setF((s) => ({ ...s, plProfile: "" }));
      onSaved();
    }
  }

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setF((s) => ({ ...s, [k]: e.target.value }));

  return (
    <form onSubmit={save} className="card space-y-3 p-4 text-sm">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label>
          <div className="text-xs text-[var(--muted)]">League ID</div>
          <input className="input w-full" value={f.leagueId} onChange={set("leagueId")}
            placeholder="draft.premierleague.com/league/…/standings" />
        </label>
        <label>
          <div className="text-xs text-[var(--muted)]">Your entry ID (team)</div>
          <input className="input w-full" value={f.entryId} onChange={set("entryId")}
            placeholder="from your team URL /entry/<id>/event/…" />
        </label>
      </div>
      <div className="border-t border-[var(--border)] pt-3">
        <div className="text-xs text-[var(--muted)]">
          <b>Optional</b> — the FPL Draft API is public, so league standings,
          ownership and squads all sync without a cookie. Only add{" "}
          <code>pl_profile</code> (DevTools → Application → Cookies →
          draft.premierleague.com) if a call starts returning 403.
          {hasCookie && <b className="text-[var(--good)]"> stored ✓</b>}
        </div>
        <input
          className="input mt-2 w-full font-mono text-xs"
          value={f.plProfile}
          onChange={set("plProfile")}
          placeholder="pl_profile = eyJ…  (or paste the whole cookie string)"
        />
      </div>
      <div className="flex items-center gap-3">
        <button type="submit" className="btn btn-primary">Save</button>
        {msg && <span className="text-[var(--muted)]">{msg}</span>}
      </div>
    </form>
  );
}
