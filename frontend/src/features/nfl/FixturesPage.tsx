import { $api, type Api } from "@/api/client";
import { BYE_BG, FDR_BG } from "@/shared/fdr";
import { fmt } from "@/shared/format";
import { EmptyState, Legend, QueryView } from "@/shared/ui";

export default function NflFixturesPage() {
  const q = $api.useQuery("get", "/api/nfl/fixtures");
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Fixture ticker</h1>
      <QueryView query={q}>{(d) => <Ticker d={d} />}</QueryView>
    </div>
  );
}

function Ticker({ d }: { d: Api["NflFixturesResponse"] }) {
  if (d.clubs.length === 0) return <EmptyState title="No fixtures yet" hint="Waiting for the first NFL sync." />;
  return (
    <>
      <p className="text-sm text-[var(--muted)]">
        Every NFL team, next {d.weeks.length} weeks — matchup difficulty for that team's skill players (opponent defence
        vs the run/pass). Easiest run first: target streamers, DST and buy-low windows.
      </p>
      <div className="card table-wrap">
        <table className="dtable text-xs">
          <thead>
            <tr>
              <th className="sticky left-0 bg-[var(--surface)]">Team</th>
              {d.weeks.map((w) => (
                <th key={w} className="num">W{w}</th>
              ))}
              <th className="num">Avg</th>
            </tr>
          </thead>
          <tbody>
            {d.clubs.map((c) => (
              <tr key={c.team}>
                <td className="sticky left-0 bg-[var(--surface)] font-medium">{c.team}</td>
                {c.cells.map((cell) => (
                  <td key={cell.week} className="num" title={cell.fdr ? `difficulty ${cell.fdr}/5` : ""}
                    style={{ background: cell.opp === "BYE" ? BYE_BG : cell.fdr ? FDR_BG[cell.fdr] : undefined }}>
                    {cell.opp || "–"}
                    {cell.opp && cell.opp !== "BYE" && <span className="ml-1 text-[9px] text-[var(--muted)]">{cell.home ? "H" : "A"}</span>}
                  </td>
                ))}
                <td className="num font-semibold">{fmt(c.avgFdr, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Legend
        items={[
          ["Green (1–2)", "soft matchup — start that team's skill players; streaming the opposing DST is risky"],
          ["Red (4–5)", "tough — fade, consider a bye/streamer instead"],
          ["grey BYE", "team is on bye that week"],
          ["Avg", "mean difficulty over the shown weeks"],
        ]}
      />
    </>
  );
}
