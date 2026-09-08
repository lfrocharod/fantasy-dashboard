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
          <b>Login token</b> — optional. Standings, ownership and rosters sync
          without it, but it&apos;s what lets us read your{" "}
          <b>live Pick Team</b> (this week&apos;s starting XI + captain) before the
          deadline, instead of just your last fielded team.
          {hasCookie && <b className="text-[var(--good)]"> stored ✓</b>}
          <div className="mt-1">
            Sign in at <span className="font-mono">draft.premierleague.com</span>,
            open <b>Pick Team</b>, then <b>F12 → Network</b> → reload → right-click
            any <span className="font-mono">api/</span> request →{" "}
            <b>Copy → Copy as cURL</b> → paste the whole thing below. (Or just the{" "}
            <span className="font-mono">x-api-authorization: Bearer …</span> value.)
            Stored AES-encrypted. The token lasts ~8 h, so re-paste it when you want
            a pre-deadline look; after each deadline your real XI syncs on its own.
          </div>
        </div>
        <textarea
          className="input mt-2 h-20 w-full font-mono text-[11px]"
          value={f.plProfile}
          onChange={(e) => setF((s) => ({ ...s, plProfile: e.target.value }))}
          placeholder="paste the curl command, or  Bearer eyJ…"
        />
      </div>
      <div className="flex items-center gap-3">
        <button type="submit" className="btn btn-primary">Save</button>
        {msg && <span className="text-[var(--muted)]">{msg}</span>}
      </div>
    </form>
  );
}
