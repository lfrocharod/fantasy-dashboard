import { useMemo, useState } from "react";
import { $api, type Api } from "@/api/client";
import { fmt } from "@/shared/format";
import { EmptyState, Legend, PosBadge, QueryView, Range, Toggle } from "@/shared/ui";
import { Flags, startPct, type Player } from "./common";

const POS = ["ALL", "GKP", "DEF", "MID", "FWD"] as const;
type Pos = (typeof POS)[number];
const SORTS = {
  horizon: "next 6 GW", proj: "next GW", ml: "next GW (ML)", vbd: "value over replacement", csProb: "clean-sheet %",
  form: "form", totalPoints: "total points", xgi90: "xGI/90", ict90: "ICT/90", thr90: "Threat/90",
  cre90: "Creativity/90",
} as const;
type Sort = keyof typeof SORTS;

export default function FplPlayersPage() {
  const q = $api.useQuery("get", "/api/fpl/board");
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Players &amp; free-agent finder</h1>
      <QueryView query={q}>{(d) => <Players d={d} />}</QueryView>
    </div>
  );
}

function Players({ d }: { d: Api["BoardResponse"] }) {
  const [pos, setPos] = useState<Pos>("ALL");
  const [sort, setSort] = useState<Sort>("horizon");
  const [search, setSearch] = useState("");
  const [availableOnly, setAvailableOnly] = useState(true);
  const mine = useMemo(() => new Set(d.myIds), [d.myIds]);

  const list = useMemo(() => {
    const s = search.trim().toLowerCase();
    return d.players
      .filter((p) => (pos === "ALL" || p.pos === pos) && (!availableOnly || p.available) && (!s || p.name.toLowerCase().includes(s)))
      .sort((a: Player, b: Player) => (b[sort] ?? -1) - (a[sort] ?? -1) || b.horizon - a.horizon)
      .slice(0, 250);
  }, [d.players, pos, availableOnly, search, sort]);

  if (d.players.length === 0) return <EmptyState title="No players yet" hint="Waiting for the first FPL sync." />;
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <Toggle value={pos} options={POS} onChange={setPos} />
        <label className="ml-2 flex items-center gap-1 text-xs">
          <input type="checkbox" checked={availableOnly} onChange={(e) => setAvailableOnly(e.target.checked)} />
          free agents only
        </label>
        <select className="input ml-auto text-xs" value={sort} onChange={(e) => setSort(e.target.value as Sort)} aria-label="sort by">
          {Object.entries(SORTS).map(([k, label]) => (
            <option key={k} value={k}>Sort: {label}</option>
          ))}
        </select>
        <input className="input text-xs" placeholder="search…" value={search} onChange={(e) => setSearch(e.target.value)} />
        <span className="text-xs text-[var(--muted)]">{list.length} shown</span>
      </div>

      <div className="card table-wrap">
        <table className="dtable">
          <thead>
            <tr>
              <th>Pos</th>
              <th>Player</th>
              <th className="hide-sm">Team</th>
              <th>Opp</th>
              <th className="num">xPts</th>
              <th className="num" title="the learned model's expected points next gameweek (see the backtest report)">ML</th>
              <th className="num hide-sm">Range</th>
              <th className="num" title={`sum of projected points over the next ${d.gws.length} gameweeks`}>xPts·{d.gws.length}</th>
              <th className="num hide-sm">Start%</th>
              <th className="num hide-sm">CS%</th>
              <th className="num hide-sm">xGI90</th>
              <th className="num hide-sm">ICT90</th>
              <th className="num hide-sm" title="expected goals conceded per 90 while on the pitch — lower is better for DEF/GK value">xGC90</th>
              <th className="num hide-sm">Form</th>
              <th>Owner</th>
            </tr>
          </thead>
          <tbody>
            {list.map((p) => (
              <tr key={p.extId} style={mine.has(p.extId) ? { background: "rgba(31,111,235,0.08)" } : undefined}>
                <td>
                  <PosBadge position={p.pos} small />
                </td>
                <td className="font-medium">
                  {p.name}
                  <Flags p={p} value />
                </td>
                <td className="hide-sm">{p.team}</td>
                <td className="text-xs text-[var(--muted)]">{p.nextOpp}</td>
                <td className="num">{fmt(p.proj)}</td>
                <td className="num text-[var(--muted)]">{fmt(p.ml)}</td>
                <td className="num hide-sm">
                  <Range lo={p.gws[0]?.lo ?? 0} hi={p.gws[0]?.hi ?? 0} mean={p.proj} digits={1} />
                </td>
                <td className="num font-semibold">{fmt(p.horizon, 0)}</td>
                <td className="num hide-sm">{startPct(p.pStart)}</td>
                <td className="num hide-sm">{p.pos === "FWD" ? "–" : Math.round(p.csProb * 100)}</td>
                <td className="num hide-sm">{fmt(p.xgi90, 2)}</td>
                <td className="num hide-sm"
                  title={p.ict90 ? `Influence ${fmt(p.inf90)} · Creativity ${fmt(p.cre90)} · Threat ${fmt(p.thr90)} (per 90)` : ""}>
                  {p.ict90 ? fmt(p.ict90) : "–"}
                </td>
                <td className="num hide-sm">{p.pos === "FWD" || !p.xgc90 ? "–" : fmt(p.xgc90, 2)}</td>
                <td className="num hide-sm">{fmt(p.form)}</td>
                <td className="text-xs">
                  {mine.has(p.extId) ? (
                    <span className="text-[var(--accent)]">you</span>
                  ) : p.available ? (
                    <span className="text-[var(--good)]">FA</span>
                  ) : (
                    <span className="text-[var(--muted)]">{p.ownerName || "owned"}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Legend
        items={[
          ["xPts / xPts·N", "projected draft points — next gameweek, then the sum over the next N shown"],
          ["ML", "a second opinion: gradient-boosted trees trained on seven seasons of public FPL data, backtested walk-forward (graded weekly on the Overview)"],
          ["Range", "~15th–85th percentile next-GW outcome (blank · mean · haul) — wider for boom/bust attackers, tighter for a nailed defender's appearance + DEFCON floor"],
          ["Start%", "modelled chance of starting the next match"],
          ["CS%", "clean-sheet probability (opponent attack vs your team's defence). GKP/DEF worth 4, MID 1"],
          ["xGI90", "expected goal involvements per 90 — non-penalty xG + xA, this Premier League season"],
          ["ICT90", "FPL's Influence-Creativity-Threat index per 90 (hover for the I/C/T split), this Premier League season"],
          ["xGC90", "expected goals conceded per 90 while on the pitch — defensive solidity for GK/DEF/MID value; lower is better. Hidden for forwards."],
          ["value / output-led", "underlying numbers better than (value) or worse than (output-led) the points so far"],
          ["P / F / C", "first-choice penalties / free-kicks / corners"],
          ["FA", "free agent in your league; a name = the manager who has them"],
        ]}
      />
    </>
  );
}
