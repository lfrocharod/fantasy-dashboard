import { useMemo, useState } from "react";
import { $api, type Api } from "@/api/client";
import { FDR_BG } from "@/shared/fdr";
import { EmptyState, Legend, QueryView, Toggle } from "@/shared/ui";

type View = "att" | "def" | "blend";
const LABEL: Record<View, string> = { att: "For attackers", def: "For defenders / GK", blend: "Blended" };
type Cell = Api["TickerCell"];
const pick = (v: View) => (c: Cell) => (v === "att" ? c.attDifficulty : v === "def" ? c.defDifficulty : c.difficulty);

export default function FixturesPage() {
  const q = $api.useQuery("get", "/api/ucl/fixtures");
  return <QueryView query={q}>{(d) => <Grid d={d} />}</QueryView>;
}

function Grid({ d }: { d: Api["UclFixturesResponse"] }) {
  const [view, setView] = useState<View>("att");
  const sorted = useMemo(() => {
    const p = pick(view);
    const avg = (r: Api["TickerRow"]) => (r.cells.length ? r.cells.reduce((s, c) => s + p(c), 0) / r.cells.length : 0);
    return [...d.rows].sort((a, b) => avg(a) - avg(b) || a.team.localeCompare(b.team));
  }, [d.rows, view]);
  if (d.rows.length === 0) return <EmptyState title="No upcoming fixtures" />;
  const p = pick(view);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm text-[var(--muted)]">
          {view === "att"
            ? "How hard it is to get goals / assists — the opponent's defensive solidity."
            : view === "def"
              ? "How hard it is to keep a clean sheet — the opponent's attacking threat."
              : "A blend of both sides."}{" "}
          Easiest run first.
        </p>
        <div className="ml-auto">
          <Toggle value={view} options={["att", "def", "blend"] as const} label={(v) => LABEL[v]} onChange={setView} />
        </div>
      </div>
      <div className="card table-wrap">
        <table className="dtable">
          <thead>
            <tr>
              <th>Team</th>
              {d.matchdays.map((m) => (
                <th key={m} className="num">MD{m}</th>
              ))}
              <th className="num">Avg</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => {
              const avg = r.cells.length ? r.cells.reduce((s, c) => s + p(c), 0) / r.cells.length : 0;
              return (
                <tr key={r.teamId}>
                  <td className="whitespace-nowrap font-medium">{r.team}</td>
                  {d.matchdays.map((m) => {
                    const c = r.cells.find((x) => x.matchday === m);
                    if (!c) return <td key={m} className="num text-[var(--muted)]">–</td>;
                    return (
                      <td key={m} className="num" style={{ background: FDR_BG[p(c)] }}
                        title={`${c.home ? "vs" : "@"} ${c.opp} — ${LABEL[view].toLowerCase()} ${p(c)}/5`}>
                        <span className="font-semibold">{c.oppCode || c.opp.slice(0, 3).toUpperCase()}</span>
                        <span className="ml-1 text-[10px] text-[var(--muted)]">{c.home ? "H" : "A"}</span>
                      </td>
                    );
                  })}
                  <td className="num font-semibold">{avg.toFixed(1)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <Legend
        items={[
          ["For attackers", "opponent's defensive strength — green = leaky, target their forwards"],
          ["For defenders / GK", "opponent's attacking threat — green = clean sheets likely"],
          ["Green / Grey / Red", "easy / neutral / tough"],
          ["Avg", "mean over the shown matchdays for the selected view"],
        ]}
      />
    </div>
  );
}
