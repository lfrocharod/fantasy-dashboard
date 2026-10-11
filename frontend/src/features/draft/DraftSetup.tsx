import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";
import { $api, fetchClient, type Api } from "@/api/client";
import { parseEspnTeamUrl } from "@/features/nba/common";

type Sport = "fpl" | "nfl" | "nba";
type Update = Api["DraftConfigUpdate"];

/** League connection for FPL Draft and the ESPN leagues (NFL, NBA).
 * Secrets are write-only: the form shows whether one is stored, never its value. */
export function DraftSetup({ sport }: { sport: Sport }) {
  const q = $api.useQuery("get", "/api/settings/draft", { params: { query: { sport } } });
  if (!q.data) return <div className="card p-4 text-sm text-[var(--muted)]">Loading setup…</div>;
  if (sport === "fpl") return <FplForm cfg={q.data} />;
  return sport === "nba" ? <NbaForm cfg={q.data} /> : <NflForm cfg={q.data} />;
}

function useSave(sport: Sport) {
  const qc = useQueryClient();
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function save(body: Update): Promise<boolean> {
    setBusy(true);
    setMsg(null);
    const { response } = await fetchClient.POST("/api/settings/draft", { body: { ...body, sport } });
    setBusy(false);
    setMsg(
      response.ok ? "Saved — the next scheduled sync applies it." : response.status === 403 ? "Read-only demo." : "Save failed",
    );
    if (response.ok) await qc.invalidateQueries();
    return response.ok;
  }
  return { save, msg, busy };
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <div className="text-xs text-[var(--muted)]">{label}</div>
      {children}
    </label>
  );
}

function Actions({ busy, msg }: { busy: boolean; msg: string | null }) {
  return (
    <div className="flex items-center gap-3">
      <button type="submit" className="btn btn-primary" disabled={busy}>
        {busy ? "Saving…" : "Save"}
      </button>
      {msg && <span className="text-[var(--muted)]">{msg}</span>}
    </div>
  );
}

function FplForm({ cfg }: { cfg: Api["DraftConfig"] }) {
  const { save, msg, busy } = useSave("fpl");
  const [leagueId, setLeagueId] = useState(cfg.leagueId);
  const [entryId, setEntryId] = useState(cfg.entryId);
  const [token, setToken] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    const ok = await save({
      leagueId: leagueId.trim() || null,
      entryId: entryId.trim() || null,
      ...(token.trim() ? { plProfile: token.trim() } : {}),
    });
    if (ok) setToken("");
  }

  return (
    <form onSubmit={submit} className="card space-y-3 p-4 text-sm">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="League ID">
          <input className="input w-full" value={leagueId} onChange={(e) => setLeagueId(e.target.value)}
            placeholder="draft.premierleague.com/league/…/standings" />
        </Field>
        <Field label="Your entry ID (team)">
          <input className="input w-full" value={entryId} onChange={(e) => setEntryId(e.target.value)}
            placeholder="from your team URL /entry/<id>/event/…" />
        </Field>
      </div>
      <div className="border-t border-[var(--border)] pt-3">
        <div className="text-xs text-[var(--muted)]">
          <b>Login token</b> — optional. Standings, ownership and rosters sync without it, but it's what lets us read
          your <b>live Pick Team</b> (this week's starting XI) before the deadline, instead of just your last fielded
          team.
          {cfg.hasCookies && <b className="text-[var(--good)]"> stored ✓</b>}
          <div className="mt-1">
            Sign in at <span className="font-mono">draft.premierleague.com</span>, open <b>Pick Team</b>, then{" "}
            <b>F12 → Network</b> → reload → right-click any <span className="font-mono">api/</span> request →{" "}
            <b>Copy → Copy as cURL</b> → paste the whole thing below (or just the{" "}
            <span className="font-mono">x-api-authorization: Bearer …</span> value). Stored encrypted. The token lasts
            ~8 h, so re-paste it when you want a pre-deadline look; after each deadline your real XI syncs on its own.
          </div>
        </div>
        <textarea className="input mt-2 h-20 w-full font-mono text-[11px]" value={token}
          onChange={(e) => setToken(e.target.value)} placeholder="paste the curl command, or  Bearer eyJ…" />
      </div>
      <Actions busy={busy} msg={msg} />
    </form>
  );
}

const num = (s: string): number | null => (s.trim() && Number.isFinite(Number(s)) ? Number(s) : null);

function NflForm({ cfg }: { cfg: Api["DraftConfig"] }) {
  const { save, msg, busy } = useSave("nfl");
  const [f, setF] = useState(() => ({
    leagueId: cfg.leagueId, myTeamId: cfg.myTeamId, mySlot: cfg.mySlot, teams: cfg.teams || "12",
    scoring: cfg.scoring || "ppr", year: cfg.year || String(new Date().getFullYear()),
  }));
  const [espnS2, setEspnS2] = useState("");
  const [swid, setSwid] = useState("");
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((s) => ({ ...s, [k]: e.target.value }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    const ok = await save({
      leagueId: f.leagueId.trim(),
      scoring: f.scoring as Update["scoring"],
      myTeamId: num(f.myTeamId),
      mySlot: num(f.mySlot),
      teams: num(f.teams),
      year: num(f.year),
      ...(espnS2.trim() ? { espnS2: espnS2.trim() } : {}),
      ...(swid.trim() ? { swid: swid.trim() } : {}),
    });
    if (ok) {
      setEspnS2("");
      setSwid("");
    }
  }

  return (
    <form onSubmit={submit} className="card space-y-3 p-4 text-sm">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Field label="Draft slot (your pick #)">
          <input className="input w-full" inputMode="numeric" value={f.mySlot} onChange={set("mySlot")} placeholder="e.g. 6" />
        </Field>
        <Field label="# teams">
          <input className="input w-full" inputMode="numeric" value={f.teams} onChange={set("teams")} />
        </Field>
        <Field label="Scoring">
          <select className="input w-full" value={f.scoring} onChange={set("scoring")}>
            <option value="ppr">PPR</option>
            <option value="half">Half-PPR</option>
            <option value="standard">Standard</option>
          </select>
        </Field>
        <Field label="ESPN league ID">
          <input className="input w-full" value={f.leagueId} onChange={set("leagueId")} />
        </Field>
        <Field label="Your ESPN team ID">
          <input className="input w-full" inputMode="numeric" value={f.myTeamId} onChange={set("myTeamId")} placeholder="for is-mine tagging" />
        </Field>
        <Field label="Season">
          <input className="input w-full" inputMode="numeric" value={f.year} onChange={set("year")} />
        </Field>
      </div>
      <div className="border-t border-[var(--border)] pt-3">
        <div className="text-xs text-[var(--muted)]">
          ESPN cookies (for private leagues: live pick sync and real roster rules) — DevTools → Application → Cookies →
          fantasy.espn.com. {cfg.hasCookies && <b className="text-[var(--good)]">stored ✓</b>}
        </div>
        <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
          <input className="input font-mono text-xs" value={espnS2} onChange={(e) => setEspnS2(e.target.value)} placeholder="espn_s2 = …" />
          <input className="input font-mono text-xs" value={swid} onChange={(e) => setSwid(e.target.value)} placeholder="SWID = {…}" />
        </div>
      </div>
      <Actions busy={busy} msg={msg} />
    </form>
  );
}

function NbaForm({ cfg }: { cfg: Api["DraftConfig"] }) {
  const { save, msg, busy } = useSave("nba");
  const [f, setF] = useState(() => ({ leagueId: cfg.leagueId, myTeamId: cfg.myTeamId, year: cfg.year }));
  const [url, setUrl] = useState("");
  const [espnS2, setEspnS2] = useState("");
  const [swid, setSwid] = useState("");
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((s) => ({ ...s, [k]: e.target.value }));

  function fromUrl(v: string) {
    setUrl(v);
    const p = parseEspnTeamUrl(v);
    setF((s) => ({ leagueId: p.leagueId ?? s.leagueId, myTeamId: p.teamId ?? s.myTeamId, year: p.seasonId ?? s.year }));
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    const ok = await save({
      leagueId: f.leagueId.trim(),
      myTeamId: num(f.myTeamId),
      year: num(f.year),
      ...(espnS2.trim() ? { espnS2: espnS2.trim() } : {}),
      ...(swid.trim() ? { swid: swid.trim() } : {}),
    });
    if (ok) {
      setEspnS2("");
      setSwid("");
      setUrl("");
    }
  }

  return (
    <form onSubmit={submit} className="card space-y-3 p-4 text-sm">
      <Field label="Your ESPN team page URL — fills in the rest">
        <input className="input w-full font-mono text-xs" value={url} onChange={(e) => fromUrl(e.target.value)}
          placeholder="https://fantasy.espn.com/basketball/team?leagueId=…&teamId=…&seasonId=…" />
      </Field>
      <div className="grid grid-cols-3 gap-3">
        <Field label="ESPN league ID">
          <input className="input w-full" value={f.leagueId} onChange={set("leagueId")} />
        </Field>
        <Field label="Your team ID">
          <input className="input w-full" inputMode="numeric" value={f.myTeamId} onChange={set("myTeamId")} />
        </Field>
        <Field label="Season (the year it ends)">
          <input className="input w-full" inputMode="numeric" value={f.year} onChange={set("year")} />
        </Field>
      </div>
      <div className="border-t border-[var(--border)] pt-3">
        <div className="text-xs text-[var(--muted)]">
          ESPN login — only needed for a private league.{" "}
          {cfg.hasCookies ? (
            <b className="text-[var(--good)]">stored ✓</b>
          ) : cfg.sharedLogin ? (
            <b className="text-[var(--good)]">Using your NFL login (same ESPN account) — leave these blank.</b>
          ) : (
            "DevTools → Application → Cookies → fantasy.espn.com."
          )}
        </div>
        <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
          <input className="input font-mono text-xs" value={espnS2} onChange={(e) => setEspnS2(e.target.value)} placeholder="espn_s2 = …" />
          <input className="input font-mono text-xs" value={swid} onChange={(e) => setSwid(e.target.value)} placeholder="SWID = {…}" />
        </div>
      </div>
      <Actions busy={busy} msg={msg} />
    </form>
  );
}
