import { $api, type Api } from "@/api/client";
import { BYE_BG, FDR_BG } from "@/shared/fdr";
import { fmt } from "@/shared/format";
import { EmptyState, Legend, PosBadge, QueryView, Section } from "@/shared/ui";

export default function NflTeamsPage() {
  const q = $api.useQuery("get", "/api/nfl/teams");
  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold">Team watch</h1>
      <QueryView query={q}>{(d) => <Clubs clubs={d.clubs} />}</QueryView>
    </div>
  );
}

export function WeekChip({ c }: { c: Api["WeekOpp"] }) {
  const bye = c.opp === "BYE";
  return (
    <span className="rounded px-2 py-1 text-xs" style={{ background: bye ? BYE_BG : c.fdr ? FDR_BG[c.fdr] : undefined }}>
      W{c.week} {bye ? "BYE" : `${c.home ? "v" : "@"} ${c.opp}`}
    </span>
  );
}

function Clubs({ clubs }: { clubs: Api["NflClubDossier"][] }) {
  if (clubs.length === 0) return <EmptyState title="No teams yet" hint="Waiting for the first NFL sync." />;
  return (
    <>
      <p className="text-sm text-[var(--muted)]">
        One card per NFL team, easiest fixture run first: the fantasy-relevant projected starters (QB1, RB1-2, WR1-3,
        TE1), injury designations, bye week, and the next weeks' matchups.
      </p>
      {clubs.map((d) => (
        <Section key={d.team} title={d.team}
          right={<span className="text-xs text-[var(--muted)]">avg matchup {fmt(d.avgFdr, 1)}{d.bye ? ` · bye W${d.bye}` : ""}</span>}>
          <div className="card space-y-3 p-3">
            <div className="flex flex-wrap gap-1">
              {d.fixtures.map((c) => (
                <WeekChip key={c.week} c={c} />
              ))}
            </div>
            <div className="table-wrap">
              <table className="dtable">
                <thead>
                  <tr>
                    <th>Pos</th>
                    <th>Projected starter</th>
                    <th className="num">Start%</th>
                    <th className="num">Wk proj</th>
                    <th className="num">ROS</th>
                    <th className="hide-sm">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {d.starters.map((p) => (
                    <tr key={p.extId}>
                      <td>
                        <PosBadge position={p.pos} small />
                      </td>
                      <td className="font-medium">{p.name}</td>
                      <td className="num">{p.pctStarted ? `${Math.round(p.pctStarted)}%` : "–"}</td>
                      <td className="num font-semibold">{fmt(p.weekProj)}</td>
                      <td className="num">{fmt(p.rosProj, 0)}</td>
                      <td className="hide-sm text-xs text-[var(--muted)]">{p.injury !== "ACTIVE" ? p.injury : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {d.bench.length > 0 && (
              <div className="text-xs text-[var(--muted)]">
                <span className="font-semibold text-[var(--text)]">Next man up: </span>
                {d.bench.map((p) => `${p.name} (${p.pos})`).join(", ")}
              </div>
            )}
            {d.doubts.length > 0 && (
              <div className="text-xs text-[var(--muted)]">
                <span className="font-semibold text-[var(--text)]">Injury report: </span>
                {d.doubts.slice(0, 8).map((p) => `${p.name} (${p.injury})`).join(", ")}
              </div>
            )}
          </div>
        </Section>
      ))}
      <Legend
        items={[
          ["Start%", "share of ESPN leagues starting this player — the crowd's read on the depth chart"],
          ["Wk proj / ROS", "projected PPR points this week / rest of season"],
          ["Fixture chip", "difficulty 1 (green) … 5 (red); grey = bye"],
          ["Projected starter", "most-started player at that slot who isn't OUT/IR"],
        ]}
      />
    </>
  );
}
