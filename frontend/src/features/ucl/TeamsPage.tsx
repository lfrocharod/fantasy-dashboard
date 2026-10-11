import { $api, type Api } from "@/api/client";
import { FDR_BG } from "@/shared/fdr";
import { fmt } from "@/shared/format";
import { EmptyState, Legend, PosBadge, QueryView, Section } from "@/shared/ui";

const startPct = (p: Api["PlayerRow"]) => (p.startPct != null ? `${Math.round(p.startPct * 100)}%` : "–");

export default function TeamsPage() {
  const q = $api.useQuery("get", "/api/ucl/teams");
  return <QueryView query={q}>{(d) => <Teams d={d} />}</QueryView>;
}

function Teams({ d }: { d: Api["UclTeamsResponse"] }) {
  if (d.teams.length === 0) return <EmptyState title="No team data yet" hint="Waiting for the first sync." />;
  return (
    <div className="space-y-6">
      <p className="text-sm text-[var(--muted)]">
        One card per club, easiest fixture run first: strength, the next five matchdays, a formation-legal probable
        XI with start chances, set-piece duty, injury and rotation doubts, and anyone our roster still lists here who
        has moved on.
      </p>
      {d.teams.map((t) => (
        <Section
          key={t.teamId}
          title={t.team}
          right={
            <span className="text-xs text-[var(--muted)]">
              {t.tier} · atk {fmt(t.attackRating, 2)} · def {fmt(t.defenceRating, 2)}
            </span>
          }
        >
          <div className="card space-y-3 p-3">
            <div className="flex flex-wrap gap-1">
              {t.fixtures.map((c) => (
                <span key={c.matchday} className="rounded px-2 py-1 text-xs" style={{ background: FDR_BG[c.difficulty] }}
                  title={`MD${c.matchday} · difficulty ${c.difficulty}/5`}>
                  MD{c.matchday} {c.home ? "v" : "@"} {c.oppCode || c.opp.slice(0, 3).toUpperCase()}
                </span>
              ))}
              {t.fixtures.length === 0 && <span className="text-xs text-[var(--muted)]">no upcoming league-phase fixtures</span>}
            </div>
            <div className="grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <div className="text-xs font-semibold text-[var(--muted)]">SET PIECES</div>
                <div>PK: {t.setPieces.pk?.length ? t.setPieces.pk.map((p) => p.name).join(", ") : <span className="text-[var(--muted)]">unknown</span>}</div>
                {!!t.setPieces.fk?.length && <div>FK: {t.setPieces.fk.map((p) => p.name).join(", ")}</div>}
                {!!t.setPieces.ck?.length && <div>CK: {t.setPieces.ck.map((p) => p.name).join(", ")}</div>}
              </div>
              <div>
                <div className="text-xs font-semibold text-[var(--muted)]">DOUBTS / OUT</div>
                {t.doubts.length ? (
                  t.doubts.slice(0, 6).map((p) => (
                    <div key={p.playerId}>
                      {p.name}{" "}
                      <span className="text-[var(--muted)]">
                        {p.statusCode >= 2 ? "out" : "doubt"}
                        {p.statusDetail ? ` (${p.statusDetail})` : ""}
                      </span>
                    </div>
                  ))
                ) : (
                  <div className="text-[var(--muted)]">none flagged</div>
                )}
                {t.movedOn.map((p) => (
                  <div key={p.playerId} className="text-[var(--warn)]">
                    {p.name} — {p.roleNote || "form data points elsewhere"}
                  </div>
                ))}
              </div>
            </div>
            <div className="table-wrap">
              <table className="dtable">
                <thead>
                  <tr>
                    <th>Pos</th>
                    <th>Probable XI</th>
                    <th className="num">Start%</th>
                    <th className="num hide-sm">L5 G+A</th>
                    <th className="num">Hot</th>
                    <th className="num">xPts (MD{d.matchday})</th>
                  </tr>
                </thead>
                <tbody>
                  {t.probableXi.map((p) => (
                    <tr key={p.playerId}>
                      <td>
                        <PosBadge position={p.position} />
                        {p.role && p.role !== p.position && <span className="ml-1 text-[11px] font-semibold text-[var(--warn)]">→{p.role}</span>}
                      </td>
                      <td className="font-medium">
                        {p.name}
                        {p.setPiece && (
                          <span className="ml-1 rounded border border-[var(--border)] px-1 text-[10px] font-semibold text-[var(--accent)]">
                            {p.setPiece.replace("PK2", "PK²")}
                          </span>
                        )}
                      </td>
                      <td className="num">
                        {startPct(p)}
                        {p.confirmed === "start" && <span className="ml-1 text-[var(--good)]">✓</span>}
                        {p.confirmed === "bench" && <span className="ml-1 text-[var(--muted)]">⑂</span>}
                      </td>
                      <td className="num hide-sm">{fmt(p.recentGoalInvolvements, 0)}</td>
                      <td className="num">{p.hotScore ? fmt(p.hotScore, 2) : "–"}</td>
                      <td className="num font-semibold">{fmt(p.xpts)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {t.bench.length > 0 && (
              <div className="text-xs text-[var(--muted)]">
                <span className="font-semibold text-[var(--text)]">Also in the pool: </span>
                {t.bench.map((p) => `${p.name} (${p.position}, ${startPct(p)})`).join(", ")}
              </div>
            )}
          </div>
        </Section>
      ))}
      <Legend
        items={[
          ["Fixture chip", "difficulty 1 (green) … 5 (red); v / @ = home / away"],
          ["tier / atk / def", "club strength: atk >1 scores more than average, def >1 concedes more"],
          ["PK / FK / CK", "penalty / free-kick / corner duty (best guess — set_piece_roles corrects it)"],
          ["→FWD", "our position label vs the role they've actually been playing"],
          ["✓ / ⑂", "in the confirmed starting XI / confirmed benched"],
          ["Hot", "recent goal involvement per 90"],
        ]}
      />
    </div>
  );
}
