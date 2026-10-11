import { useMemo, useState } from "react";
import { $api, type Api } from "@/api/client";
import { FDR_BG } from "@/shared/fdr";
import { fmt } from "@/shared/format";
import { EmptyState, Legend, QueryView, Toggle } from "@/shared/ui";

type View = "att" | "def" | "blend";
const LABEL: Record<View, string> = { att: "For attackers", def: "For defenders / GK", blend: "Blended" };
type Cell = Api["ClubCell"];
const pick = (v: View) => (c: Cell) => (v === "att" ? c.fdrAtt : v === "def" ? c.fdrDef : c.fdr);
const avg = (cells: Cell[], p: (c: Cell) => number) => {
  const r = cells.filter((c) => p(c));
  return r.length ? r.reduce((a, c) => a + p(c), 0) / r.length : 3;
};

export default function FplFixturesPage() {
  const q = $api.useQuery("get", "/api/fpl/fixtures");
  return <QueryView query={q}>{(d) => <Ticker d={d} />}</QueryView>;
}

function Ticker({ d }: { d: Api["FplFixturesResponse"] }) {
  const [view, setView] = useState<View>("att");
  const p = pick(view);
  const sorted = useMemo(() => {
    const by = pick(view);
    return [...d.clubs].sort((a, b) => avg(a.cells, by) - avg(b.cells, by) || a.team.localeCompare(b.team));
  }, [d.clubs, view]);
  if (d.clubs.length === 0) return <EmptyState title="No fixtures yet" hint="Waiting for the first FPL sync." />;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-semibold">Fixture ticker</h1>
        <div className="ml-auto">
          <Toggle value={view} options={["att", "def", "blend"] as const} label={(v) => LABEL[v]} onChange={setView} />
        </div>
      </div>
      <p className="text-sm text-[var(--muted)]">
        {view === "att"
          ? "How hard it is to get goals / assists — the opponent's defensive solidity."
          : view === "def"
            ? "How hard it is to keep a clean sheet — the opponent's attacking threat."
            : "A 50/50 blend."}{" "}
        Every PL club, next {d.gws.length} GWs, easiest run first.
      </p>
      <div className="card table-wrap">
        <table className="dtable text-xs">
          <thead>
            <tr>
              <th className="sticky left-0 bg-[var(--surface)]">Club</th>
              {d.gws.map((g) => (
                <th key={g} className="num">GW{g}</th>
              ))}
              <th className="num">Avg</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((c) => (
              <tr key={c.team}>
                <td className="sticky left-0 bg-[var(--surface)] font-medium">{c.team}</td>
                {c.cells.map((cell) => {
                  const v = p(cell);
                  return (
                    <td key={cell.gw} className="num" style={{ background: v ? FDR_BG[v] : undefined }}
                      title={v ? `${LABEL[view].toLowerCase()} ${v}/5` : ""}>
                      {cell.opp || "–"}
                      <span className="ml-1 text-[9px] text-[var(--muted)]">{cell.home == null ? "" : cell.home ? "H" : "A"}</span>
                    </td>
                  );
                })}
                <td className="num font-semibold">{fmt(avg(c.cells, p), 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Legend
        items={[
          ["For attackers", "opponent's defensive strength — green = leaky, target this club's attackers"],
          ["For defenders / GK", "opponent's attacking threat — green = low, clean sheets likely"],
          ["Green (1–2) / Grey (3) / Red (4–5)", "easy / neutral / tough"],
          ["H / A", "home / away"],
          ["Avg", "mean over the shown gameweeks for the selected view"],
        ]}
      />
    </div>
  );
}
