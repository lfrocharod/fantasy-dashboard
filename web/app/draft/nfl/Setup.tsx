"use client";

import { useEffect, useState } from "react";

export function DraftSetup({ onSaved }: { onSaved: () => void }) {
  const [f, setF] = useState({
    leagueId: "", myTeamId: "", mySlot: "", teams: "12", scoring: "ppr", year: "2026",
    espnS2: "", swid: "",
  });
  const [hasCookies, setHasCookies] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/draft/config?sport=nfl")
      .then((r) => r.json())
      .then((d) => {
        setF((s) => ({
          ...s,
          leagueId: d.leagueId || "", myTeamId: d.myTeamId || "", mySlot: d.mySlot || "",
          teams: d.teams || "12", scoring: d.scoring || "ppr", year: d.year || "2026",
        }));
        setHasCookies(Boolean(d.hasCookies));
      });
  }, []);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    const body: Record<string, unknown> = {
      sport: "nfl",
      leagueId: f.leagueId, scoring: f.scoring,
    };
    if (f.myTeamId) body.myTeamId = Number(f.myTeamId);
    if (f.mySlot) body.mySlot = Number(f.mySlot);
    if (f.teams) body.teams = Number(f.teams);
    if (f.year) body.year = Number(f.year);
    if (f.espnS2.trim()) body.espnS2 = f.espnS2.trim();
    if (f.swid.trim()) body.swid = f.swid.trim();
    const r = await fetch("/api/draft/config", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    setMsg(r.ok ? "Saved. Re-run the ingest command to apply." : "Save failed");
    if (r.ok) {
      setF((s) => ({ ...s, espnS2: "", swid: "" }));
      onSaved();
    }
  }

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setF((s) => ({ ...s, [k]: e.target.value }));

  return (
    <form onSubmit={save} className="card space-y-3 p-4 text-sm">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <label>
          <div className="text-xs text-[var(--muted)]">Draft slot (your pick #)</div>
          <input className="input w-full" inputMode="numeric" value={f.mySlot} onChange={set("mySlot")} placeholder="e.g. 6" />
        </label>
        <label>
          <div className="text-xs text-[var(--muted)]"># teams</div>
          <input className="input w-full" inputMode="numeric" value={f.teams} onChange={set("teams")} />
        </label>
        <label>
          <div className="text-xs text-[var(--muted)]">Scoring</div>
          <select className="input w-full" value={f.scoring} onChange={set("scoring")}>
            <option value="ppr">PPR</option>
            <option value="half">Half-PPR</option>
            <option value="standard">Standard</option>
          </select>
        </label>
        <label>
          <div className="text-xs text-[var(--muted)]">ESPN league ID</div>
          <input className="input w-full" value={f.leagueId} onChange={set("leagueId")} />
        </label>
        <label>
          <div className="text-xs text-[var(--muted)]">Your ESPN team ID</div>
          <input className="input w-full" inputMode="numeric" value={f.myTeamId} onChange={set("myTeamId")} placeholder="for is-mine tagging" />
        </label>
        <label>
          <div className="text-xs text-[var(--muted)]">Season</div>
          <input className="input w-full" inputMode="numeric" value={f.year} onChange={set("year")} />
        </label>
      </div>

      <div className="border-t border-[var(--border)] pt-3">
        <div className="text-xs text-[var(--muted)]">
          ESPN cookies (for live pick sync & real roster rules) — DevTools → Application → Cookies →
          fantasy.espn.com. {hasCookies && <b className="text-[var(--good)]">stored ✓</b>}
        </div>
        <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
          <input className="input font-mono text-xs" value={f.espnS2}
            onChange={(e) => setF((s) => ({ ...s, espnS2: e.target.value }))}
            placeholder="espn_s2 = …" />
          <input className="input font-mono text-xs" value={f.swid}
            onChange={(e) => setF((s) => ({ ...s, swid: e.target.value }))}
            placeholder="SWID = {…}" />
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button type="submit" className="btn btn-primary">Save</button>
        {msg && <span className="text-[var(--muted)]">{msg}</span>}
      </div>
    </form>
  );
}
