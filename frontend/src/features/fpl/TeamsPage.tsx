import { $api, type Api } from "@/api/client";
import { FDR_BG } from "@/shared/fdr";
import { fmt } from "@/shared/format";
import { EmptyState, Legend, PosBadge, QueryView, Section } from "@/shared/ui";
import { startPct } from "./common";

export default function FplTeamsPage() {
  const q = $api.useQuery("get", "/api/fpl/teams");
  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold">Team watch</h1>
      <QueryView query={q}>{(d) => <Clubs clubs={d.clubs} />}</QueryView>
    </div>
  );
}

const names = (ps: Api["FplPlayer"][] | undefined) => (ps ?? []).map((p) => p.name).join(", ");

function Clubs({ clubs }: { clubs: Api["ClubDossier"][] }) {
  if (clubs.length === 0) return <EmptyState title="No clubs yet" hint="Waiting for the first FPL sync." />;
  return (
    <>
      <p className="text-sm text-[var(--muted)]">
        One card per Premier League club, easiest fixture run first: the probable XI (by modelled start-probability),
        set-piece takers, injury doubts, and the highest-value players. Read it to make your own calls.
      </p>
      {clubs.map((d) => (
        <Section key={d.team} title={d.team} right={<span className="text-xs text-[var(--muted)]">avg FDR {fmt(d.avgFdr, 1)}</span>}>
          <div className="card space-y-3 p-3">
            <div className="flex flex-wrap gap-1">
              {d.fixtures.map((c) => (
                <span key={c.gw} className="rounded px-2 py-1 text-xs" style={{ background: c.fdr ? FDR_BG[c.fdr] : undefined }}>
                  GW{c.gw} {c.home == null ? "" : c.home ? "v" : "@"} {c.opp}
                </span>
              ))}
            </div>
            <div className="grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <div className="text-xs font-semibold text-[var(--muted)]">SET PIECES</div>
                <div>PK: {names(d.setPieces.pk) || <span className="text-[var(--muted)]">unknown</span>}</div>
                {!!d.setPieces.fk?.length && <div>FK: {names(d.setPieces.fk)}</div>}
                {!!d.setPieces.ck?.length && <div>CK: {names(d.setPieces.ck)}</div>}
              </div>
              <div>
                <div className="text-xs font-semibold text-[var(--muted)]">DOUBTS / OUT</div>
                {d.doubts.length ? (
                  d.doubts.slice(0, 6).map((p) => (
                    <div key={p.extId}>
                      {p.name} <span className="text-[var(--muted)]">{p.news || p.status}</span>
                    </div>
                  ))
                ) : (
                  <div className="text-[var(--muted)]">none flagged</div>
                )}
              </div>
            </div>
            <div className="table-wrap">
              <table className="dtable">
                <thead>
                  <tr>
                    <th>Pos</th>
                    <th>Probable XI</th>
                    <th className="num">Start%</th>
                    <th className="num">ROS/GW</th>
                    <th className="num hide-sm">Form</th>
                  </tr>
                </thead>
                <tbody>
                  {d.probableXi.map((p) => (
                    <tr key={p.extId}>
                      <td>
                        <PosBadge position={p.pos} small />
                      </td>
                      <td className="font-medium">
                        {p.name}
                        {p.setPiece && <span className="ml-1 text-[10px] font-semibold text-[var(--accent)]">{p.setPiece.replace("PK2", "PK²")}</span>}
                      </td>
                      <td className="num">{startPct(p.pStart)}</td>
                      <td className="num font-semibold">{fmt(p.rosPpg)}</td>
                      <td className="num hide-sm">{fmt(p.form)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {d.bench.length > 0 && (
              <div className="text-xs text-[var(--muted)]">
                <span className="font-semibold text-[var(--text)]">Also in the pool: </span>
                {d.bench.map((p) => `${p.name} (${p.pos}${p.pStart ? `, ${Math.round(p.pStart * 100)}%` : ""})`).join(", ")}
              </div>
            )}
          </div>
        </Section>
      ))}
      <Legend
        items={[
          ["Start%", "modelled chance of starting the next match"],
          ["ROS/GW", "projected draft points per gameweek, rest of season"],
          ["PK / FK / CK", "penalty / free-kick / corner duty (best guess — set_piece_roles corrects it)"],
        ]}
      />
    </>
  );
}
