import { useDeferredValue, useMemo, useState } from "react";
import { $api, type Api } from "@/api/client";
import { fmt } from "@/shared/format";
import { Legend, PosBadge, QueryView, Range, StatusDot } from "@/shared/ui";

type Row = Api["PlayerRow"];
type SortKey = "xpts" | "value" | "differential" | "hotScore" | "xgi90" | "npxg90" | "xa90" | "shots90" | "price" | "selectedPct";

const SORTS: [SortKey, string][] = [
  ["xpts", "xPts"], ["value", "Value (xPts/€)"], ["differential", "Differential (xPts / owned%)"],
  ["hotScore", "Hot form"], ["xgi90", "xGI/90 (season)"], ["npxg90", "npxG/90 (season)"],
  ["xa90", "xA/90 (season)"], ["shots90", "Shots/90 (season)"], ["price", "Price"], ["selectedPct", "Ownership"],
];

function sortValue(p: Row, k: SortKey): number {
  if (k === "differential") return (p.xpts ?? 0) / Math.max(3, p.selectedPct ?? 100);
  return (p[k] as number | null | undefined) ?? -1;
}

export default function PlayersPage() {
  const [position, setPosition] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [search, setSearch] = useState("");
  const [freeOnly, setFreeOnly] = useState(true);
  const [sort, setSort] = useState<SortKey>("xpts");
  const query = {
    ...(position ? { position } : {}),
    ...(maxPrice && Number(maxPrice) > 0 ? { maxPrice: Number(maxPrice) } : {}),
    ...(search ? { search } : {}),
    limit: 250,
  };
  const deferred = useDeferredValue(query);
  const q = $api.useQuery("get", "/api/ucl/players", { params: { query: deferred } }, { placeholderData: (prev) => prev });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <div className="text-xs text-[var(--muted)]">Position</div>
          <select className="input" value={position} onChange={(e) => setPosition(e.target.value)}>
            <option value="">All</option>
            {["GK", "DEF", "MID", "FWD"].map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          <div className="text-xs text-[var(--muted)]">Max price (€m)</div>
          <input className="input w-28" inputMode="decimal" value={maxPrice} onChange={(e) => setMaxPrice(e.target.value)} placeholder="any" />
        </label>
        <label className="text-sm">
          <div className="text-xs text-[var(--muted)]">Search</div>
          <input className="input" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="name" />
        </label>
        <label className="text-sm">
          <div className="text-xs text-[var(--muted)]">Sort by</div>
          <select className="input" value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
            {SORTS.map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={freeOnly} onChange={(e) => setFreeOnly(e.target.checked)} />
          Free agents only
        </label>
      </div>
      <QueryView query={q}>{(d) => <Table data={d} sort={sort} freeOnly={freeOnly} />}</QueryView>
    </div>
  );
}

function Table({ data, sort, freeOnly }: { data: Api["UclPlayersResponse"]; sort: SortKey; freeOnly: boolean }) {
  const owned = useMemo(() => new Set(data.ownedIds), [data.ownedIds]);
  const rows = useMemo(() => {
    const list = freeOnly ? data.players.filter((p) => !owned.has(p.playerId)) : data.players;
    // price and ownership read "best" as smallest; everything else as largest
    const asc = sort === "price" || sort === "selectedPct";
    return [...list].sort((a, b) => (asc ? sortValue(a, sort) - sortValue(b, sort) : sortValue(b, sort) - sortValue(a, sort)));
  }, [data, owned, freeOnly, sort]);

  return (
    <>
      <div className="text-right text-xs text-[var(--muted)]">
        {rows.length} players · MD {data.matchday}
      </div>
      <div className="card table-wrap">
        <table className="dtable">
          <thead>
            <tr>
              <th>Pos</th>
              <th>Player</th>
              <th className="hide-sm">Team</th>
              <th className="num">Price</th>
              <th className="num hide-sm">Own%</th>
              <th className="num hide-sm">L5 G+A</th>
              <th className="num hide-sm">xGI90</th>
              <th className="num hide-sm">Sh90</th>
              <th className="num hide-sm">Rtg</th>
              <th className="num">Start%</th>
              <th className="num">xPts</th>
              <th className="num hide-sm">Range</th>
              <th className="num hide-sm">xPts(C)</th>
              <th className="num">Value</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.playerId} style={p.teamOk === false ? { opacity: 0.4 } : undefined}>
                <td>
                  <PosBadge position={p.position} />
                  {p.leverageRole && (
                    <span className="ml-1 text-[11px] font-semibold text-[var(--warn)]" title={p.roleNote ?? ""}>
                      →{p.leverageRole}
                    </span>
                  )}
                </td>
                <td>
                  {p.name} <StatusDot code={p.statusCode} detail={p.statusDetail} />
                  {p.teamOk === false && <span className="ml-1 text-[10px] text-[var(--bad)]" title={p.roleNote ?? ""}>transferred?</span>}
                  {(p.hotScore ?? 0) >= 0.9 && <span className="ml-1" title={`hot form: ${fmt(p.hotScore, 2)} G+A per 90`}>🔥</span>}
                  {p.setPiece && (
                    <span className="ml-1 rounded border border-[var(--border)] px-1 text-[10px] font-semibold text-[var(--accent)]" title="set-piece duty">
                      {p.setPiece.replace("PK2", "PK²")}
                    </span>
                  )}
                  {p.priceMomentum >= 0.25 && <span className="ml-1 text-[var(--good)]" title="price likely rising">📈</span>}
                  {p.priceMomentum <= -0.25 && <span className="ml-1 text-[var(--bad)]" title="price likely falling">📉</span>}
                  {(p.selectedPct ?? 100) < 8 && (p.xpts ?? 0) >= 4.5 && !owned.has(p.playerId) && (
                    <span className="ml-1 rounded bg-[var(--good)] px-1 text-[10px] font-semibold text-white" title="low ownership, high projection">
                      DIFF
                    </span>
                  )}
                </td>
                <td className="hide-sm">{p.teamName}</td>
                <td className="num">{fmt(p.price)}</td>
                <td className="num hide-sm">{fmt(p.selectedPct, 0)}</td>
                <td className="num hide-sm">{p.recentGoalInvolvements != null ? `${fmt(p.recentGoalInvolvements, 0)} / ${p.recentMatches}` : "–"}</td>
                <td className="num hide-sm" title={p.xgi90 != null ? `npxG/90 ${fmt(p.npxg90, 2)} + xA/90 ${fmt(p.xa90, 2)} · ${p.xgMatches} matches, ${fmt(p.xgMinutes, 0)} min` : "not enough league minutes yet"}>
                  {fmt(p.xgi90, 2)}
                </td>
                <td className="num hide-sm">{fmt(p.shots90, 1)}</td>
                <td className="num hide-sm">{p.avgRating ? fmt(p.avgRating, 1) : "–"}</td>
                <td className="num">
                  {p.startPct != null ? `${Math.round(p.startPct * 100)}%` : "–"}
                  {p.confirmed === "start" && <span className="ml-1 text-[var(--good)]" title="confirmed starting XI">✓</span>}
                  {p.confirmed === "bench" && <span className="ml-1 text-[var(--muted)]" title="confirmed on the bench">⑂</span>}
                  {p.startDisagreement >= 0.4 && <span className="ml-1 text-[var(--warn)]" title="start-probability sources disagree — rotation / fitness risk">⚠</span>}
                </td>
                <td className="num font-semibold">{fmt(p.xpts)}</td>
                <td className="num hide-sm">
                  <Range lo={p.xptsLow ?? 0} hi={p.xptsHigh ?? 0} mean={p.xpts} digits={1} />
                </td>
                <td className="num hide-sm">{fmt(p.xptsCaptain)}</td>
                <td className="num">{fmt(p.value, 2)}</td>
                <td>{owned.has(p.playerId) ? <span className="text-[var(--muted)]">owned</span> : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Legend
        items={[
          ["L5 G+A", "goals + assists over the last 5 matches (all competitions) / matches counted"],
          ["xGI90 / Sh90", "expected goal involvements and shots per 90 this domestic-league season — shown once the sample clears ~200 minutes"],
          ["Rtg", "average match rating over those games (Sofascore, ~10 scale)"],
          ["Start%", "chance of starting — the same composed number the projection uses"],
          ["⚠", "the start-probability sources disagree — a rotation or fitness question"],
          ["Range", "~15th–85th percentile outcome (blank · mean · haul)"],
          ["Value", "xPts per €m"],
          ["DIFF", "low ownership + high projection — a rank-gaining differential"],
          ["📈 / 📉", "price likely to rise / fall from transfer traffic"],
          ["PK / PK² / FK / CK", "penalty / backup-penalty / free-kick / corner duty"],
          ["→FWD", "playing further forward than UEFA lists — leverage"],
        ]}
      />
    </>
  );
}
