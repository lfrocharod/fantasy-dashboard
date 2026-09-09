import { EmptyState, Legend, PosBadge, Section } from "@/components/ui";
import { fmt } from "@/lib/format";
import { FDR_BG } from "@/lib/fdr";
import { confirmedOf, getCurrentMatchday, getTeamDossiers } from "@/lib/ucl/queries";

/** Displayed start chance: 100/0 when the official lineup is out, else the
 * composed projection, else the raw form value. Keeps this column consistent
 * with the XI the model actually picked. */
function startPct(p: {
  components?: unknown;
  pStart: number | null;
  startProb: number | null;
}): number | null {
  const c = confirmedOf(p);
  if (c === "start") return 1;
  if (c === "bench") return 0;
  return p.pStart ?? p.startProb ?? null;
}

export const dynamic = "force-dynamic";

function tier(atk: number, def: number) {
  const s = atk - (def - 1);
  if (s >= 1.35) return "elite";
  if (s >= 1.1) return "strong";
  if (s >= 0.95) return "mid";
  if (s >= 0.8) return "weak";
  return "minnow";
}

export default async function TeamWatchPage() {
  const md = await getCurrentMatchday();
  const teams = await getTeamDossiers(md);

  if (teams.length === 0) {
    return <EmptyState title="No team data yet" hint="Run ./run.sh on your machine." />;
  }

  return (
    <div className="space-y-6">
      <p className="text-sm text-[var(--muted)]">
        One card per club, sorted by easiest fixture run first. Strength rating, next 5 matchdays, a
        formation-legal probable XI (likeliest starter at each slot, with start %), the rest of the
        rotation pool, set-piece duty, injury / rotation doubts, and any player our roster still lists
        here that the form cross-check says has moved on. Use it to decide who to target for a
        specific run of games.
      </p>

      {teams.map((t) => (
        <Section
          key={t.teamId}
          title={t.team}
          right={
            <span className="text-xs text-[var(--muted)]">
              {tier(t.attackRating, t.defenceRating)} · atk {fmt(t.attackRating, 2)} · def{" "}
              {fmt(t.defenceRating, 2)}
            </span>
          }
        >
          <div className="card space-y-3 p-3">
            {/* fixture run */}
            <div className="flex flex-wrap gap-1">
              {t.fixtures.map((c) => (
                <span
                  key={c.matchday}
                  className="rounded px-2 py-1 text-xs"
                  style={{ background: FDR_BG[c.difficulty] }}
                  title={`MD${c.matchday} · difficulty ${c.difficulty}/5`}
                >
                  MD{c.matchday} {c.home ? "v" : "@"} {c.oppCode || c.opp.slice(0, 3).toUpperCase()}
                </span>
              ))}
              {t.fixtures.length === 0 && (
                <span className="text-xs text-[var(--muted)]">no upcoming league-phase fixtures</span>
              )}
            </div>

            {/* set pieces + flags */}
            <div className="grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <div className="text-xs font-semibold text-[var(--muted)]">SET PIECES</div>
                <div>
                  PK:{" "}
                  {t.setPieces.pk.length
                    ? t.setPieces.pk.map((p) => p.name).join(", ")
                    : <span className="text-[var(--muted)]">unknown</span>}
                </div>
                {t.setPieces.fk.length > 0 && <div>FK: {t.setPieces.fk.map((p) => p.name).join(", ")}</div>}
                {t.setPieces.ck.length > 0 && <div>CK: {t.setPieces.ck.map((p) => p.name).join(", ")}</div>}
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

            {/* probable XI */}
            <div className="table-wrap">
              <table className="dtable">
                <thead>
                  <tr>
                    <th>Pos</th>
                    <th>Probable XI</th>
                    <th className="num">Start%</th>
                    <th className="num hide-sm">L5 G+A</th>
                    <th className="num">Hot</th>
                    <th className="num">xPts (MD{md})</th>
                  </tr>
                </thead>
                <tbody>
                  {t.probableXI.map((p) => {
                    const sp = startPct(p);
                    const conf = confirmedOf(p);
                    const spiece = (p.setPiece ?? "").replace("PK2", "PK²");
                    return (
                      <tr key={p.playerId}>
                        <td>
                          <PosBadge position={p.position} />
                          {p.role && p.role !== p.position && (
                            <span className="ml-1 text-[11px] font-semibold text-[var(--warn)]">
                              →{p.role}
                            </span>
                          )}
                        </td>
                        <td className="font-medium">
                          {p.name}
                          {spiece && (
                            <span className="ml-1 rounded border border-[var(--border)] px-1 text-[10px] font-semibold text-[var(--accent)]">
                              {spiece}
                            </span>
                          )}
                        </td>
                        <td className="num">
                          {sp != null ? `${Math.round(sp * 100)}%` : "–"}
                          {conf === "start" && (
                            <span className="ml-1 text-[var(--good)]" title="confirmed starting XI">✓</span>
                          )}
                          {conf === "bench" && (
                            <span className="ml-1 text-[var(--muted)]" title="confirmed on the bench">⑂</span>
                          )}
                        </td>
                        <td className="num hide-sm">
                          {p.recentMatches
                            ? fmt((p.recentGoals ?? 0) + (p.recentAssists ?? 0), 0)
                            : "–"}
                        </td>
                        <td className="num">{p.hotScore ? fmt(p.hotScore, 2) : "–"}</td>
                        <td className="num font-semibold">{fmt(p.xpts)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {t.bench.length > 0 && (
              <div className="text-xs text-[var(--muted)]">
                <span className="font-semibold text-[var(--text)]">Also in the pool: </span>
                {t.bench
                  .map((p) => {
                    const sp = startPct(p);
                    return `${p.name} (${p.position}${sp != null ? `, ${Math.round(sp * 100)}%` : ""})`;
                  })
                  .join(", ")}
              </div>
            )}
          </div>
        </Section>
      ))}

      <Legend
        items={[
          ["Fixture chip", "colour = difficulty 1 (green) … 5 (red); H/A = home/away"],
          ["tier / atk / def", "club strength: atk >1 scores more than average, def >1 concedes more"],
          ["PK / FK / CK", "penalty / free-kick / corner duty (best guess — edit set_piece_roles to correct)"],
          ["→FWD", "our position label vs the role they've actually been playing"],
          ["✓ / ⑂", "in the confirmed starting XI / confirmed benched (official lineup, ~1h pre-KO)"],
          ["Hot", "recent goal involvement per 90"],
          ["moved on", "our roster still lists them here but recent match data doesn't — verify before picking"],
        ]}
      />
    </div>
  );
}
