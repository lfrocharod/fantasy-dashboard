import { $api, type Api } from "@/api/client";
import { FDR_BG } from "@/shared/fdr";
import { dateTime, fmt, signed } from "@/shared/format";
import { EmptyState, Legend, PosBadge, QueryView, Section, StatCard } from "@/shared/ui";

type Output = Api["OptimizerOutput"];
type SquadPick = Api["SquadPick"];
interface FixtureCtx {
  opp?: string | null;
  home?: boolean | null;
  fdr?: number | null;
}

export default function OptimizerPage() {
  const q = $api.useQuery("get", "/api/ucl/optimizer");
  return (
    <QueryView query={q}>
      {(d) =>
        !d.available || !d.output ? (
          <EmptyState
            title="No optimizer run yet"
            hint="The optimizer runs inside each scheduled sync, right after projections are built."
          />
        ) : d.output.preSeason && d.output.squad.length > 0 ? (
          <PreSeasonSquad data={d.output} />
        ) : (
          <Optimizer data={d.output} />
        )
      }
    </QueryView>
  );
}

function OppCell({ opp, home, fdr }: FixtureCtx) {
  if (!opp) return <td className="text-[var(--muted)]">–</td>;
  return (
    <td style={fdr ? { background: FDR_BG[fdr] } : undefined} title={fdr ? `difficulty ${fdr}/5` : ""}>
      <span className="text-[var(--muted)]">{home ? "vs" : "@"}</span> {opp}
    </td>
  );
}

function Optimizer({ data }: { data: Output }) {
  const gain = data.optimisedXpts - data.baselineXpts;
  return (
    <div className="space-y-8">
      {data.lockedMatchday != null && (
        <div className="card p-3 text-sm" style={{ borderLeft: "3px solid var(--accent)" }}>
          Matchday {data.lockedMatchday} is under way and your team is locked for it: these are transfers, chips and
          the XI for matchday {data.matchday}. UEFA applies changes saved after MD{data.lockedMatchday}&apos;s final day
          kicks off to matchday {data.matchday}.
        </div>
      )}
      {data.idealSquad && (
        <Section title="If you wildcarded now">
          <p className="text-sm text-[var(--muted)]">
            Best possible 15 for the next {data.idealSquad.horizon} matchday(s) —{" "}
            <b>{data.idealSquad.changesFromCurrent}</b> changes from your current squad, €
            {fmt(data.idealSquad.totalCost)}m, projected {fmt(data.idealSquad.horizonXpts, 0)} pts.
          </p>
          <div className="card table-wrap">
            <SquadTable picks={data.idealSquad.squad} />
          </div>
        </Section>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="Formation" value={data.formation} />
        <StatCard label="Best XI xPts" value={fmt(data.optimisedXpts)} />
        <StatCard label="Gain vs current" value={signed(gain)} sub="lineup only, no transfers" />
        <StatCard label="Horizon" value={`${data.horizon} MD`} />
      </div>

      <Section title="Recommended starting XI">
        <div className="card table-wrap">
          <table className="dtable">
            <thead>
              <tr>
                <th>Pos</th>
                <th>Player</th>
                <th>Team</th>
                <th>Opponent</th>
                <th className="num">xPts</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.bestXI.map((p) => (
                <tr key={p.playerId}>
                  <td>
                    <PosBadge position={p.position} />
                  </td>
                  <td>{p.name}</td>
                  <td>{p.team}</td>
                  <OppCell {...p} />
                  <td className="num font-semibold">{fmt(p.xpts)}</td>
                  <td>{p.isCaptain ? "(C)" : p.isVice ? "(V)" : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="Bench order">
        <div className="card table-wrap">
          <table className="dtable">
            <thead>
              <tr>
                <th>#</th>
                <th>Pos</th>
                <th>Player</th>
                <th>Opponent</th>
                <th className="num">xPts</th>
              </tr>
            </thead>
            <tbody>
              {data.bench.map((p) => (
                <tr key={p.playerId}>
                  <td>{p.order ?? ""}</td>
                  <td>
                    <PosBadge position={p.position} />
                  </td>
                  <td>{p.name}</td>
                  <OppCell {...p} />
                  <td className="num">{fmt(p.xpts)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="Transfer suggestions">
        {data.transfers.length === 0 ? (
          <p className="text-sm text-[var(--muted)]">
            No transfer improves your projected points over the next {data.horizon} matchday(s) once the –4 hit is
            accounted for. Roll the transfer.
          </p>
        ) : (
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Out</th>
                  <th>In</th>
                  <th className="num">Δ xPts ({data.horizon} MD)</th>
                  <th className="num">Hit</th>
                  <th className="num">Net</th>
                </tr>
              </thead>
              <tbody>
                {data.transfers.map((t) => (
                  <tr key={`${t.out.playerId}-${t.in.playerId}`}>
                    <td>
                      {t.out.name} <span className="text-[var(--muted)]">({t.out.team})</span>
                    </td>
                    <td>
                      {t.in.name} <span className="text-[var(--muted)]">({t.in.team})</span>
                    </td>
                    <td className="num">{fmt(t.horizonGain)}</td>
                    <td className="num">{t.hitCost ? `-${t.hitCost}` : "0"}</td>
                    <td className="num font-semibold" style={{ color: t.netGain >= 0 ? "var(--good)" : "var(--bad)" }}>
                      {signed(t.netGain)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <AnalysisSections data={data} />

      <Legend
        items={[
          ["xPts", "expected points"],
          ["MD", "matchday"],
          ["Opponent colour", "next-matchday fixture difficulty (green easy … red hard). The squad is picked to win the upcoming matchday first, then the near-term run — a hard one-off fixture can still be outweighed by a great underlying player."],
          ["EV (2×)", "expected captain points = 2 × projected points"],
          ["Ceiling / Floor", "optimistic (p85) and pessimistic (p15) captain outcomes"],
          ["Limitless / Wildcard", "the only two CL Fantasy chips — estimated extra points from playing that chip that matchday"],
          ["Δ xPts", `total xPts gained over the next ${data.horizon} matchday(s)`],
          ["Hit", "points cost of each transfer beyond your free ones (−4 each)"],
          ["Net", "Δ xPts minus the hit — only make the move if this is clearly positive"],
          ["(C)/(V)", "captain / backup captain (no formal vice in CL — you'd move the armband manually)"],
        ]}
      />
      <p className="text-xs text-[var(--muted)]">
        Generated {dateTime(data.generatedAt)} for matchday {data.matchday} (Mexico City time).
      </p>
    </div>
  );
}

const POS_ORDER: readonly string[] = ["GK", "DEF", "MID", "FWD"];

function SquadTable({ picks }: { picks: SquadPick[] }) {
  const rows = [...picks].sort(
    (a, b) =>
      POS_ORDER.indexOf(a.position) - POS_ORDER.indexOf(b.position) ||
      Number(b.isStarter) - Number(a.isStarter) ||
      b.horizonXpts - a.horizonXpts,
  );
  return (
    <table className="dtable">
      <thead>
        <tr>
          <th>Pos</th>
          <th>Player</th>
          <th>Team</th>
          <th>Opponent</th>
          <th className="num">€m</th>
          <th className="num">Proj (horizon)</th>
          <th>Role</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((p) => (
          <tr key={p.playerId} style={p.isStarter ? undefined : { opacity: 0.55 }}>
            <td>
              <PosBadge position={p.position} />
            </td>
            <td className="font-medium">{p.name}</td>
            <td>{p.team}</td>
            <OppCell {...p} />
            <td className="num">{fmt(p.price)}</td>
            <td className="num font-semibold">{fmt(p.horizonXpts, 0)}</td>
            <td>{p.isCaptain ? "Captain" : p.isVice ? "Backup (C)" : p.isStarter ? "Starter" : "Bench"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function PreSeasonSquad({ data }: { data: Output }) {
  const starters = data.squad.filter((p) => p.isStarter);
  const budget = data.budget ?? 100;
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Recommended squad to start the season</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Best legal 15 within €{fmt(budget)}m, 2·5·5·3 and max 3 per club, maximising projected points over the next{" "}
          {data.horizon} matchday(s). Your team isn’t locked until the first MD1 match kicks off, so you can build this
          for free.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="Formation" value={data.formation} />
        <StatCard label="Squad cost" value={`€${fmt(data.totalCost ?? 0)}m`} sub={`of €${fmt(budget)}m`} />
        <StatCard label="Proj. XI + captain" value={fmt(data.xiXpts ?? 0, 0)} sub="matchday 1" />
        <StatCard label="Proj. over horizon" value={fmt(data.horizonXpts ?? 0, 0)} sub={`${data.horizon} MD, all 15`} />
      </div>

      {data.changesFromCurrent != null && (
        <div className="card p-3 text-sm">
          <b>{data.changesFromCurrent}</b> changes from your current squad
          {data.keepFromCurrent != null && <> · keep {data.keepFromCurrent}</>}.
        </div>
      )}

      <Section title={`Starting XI (${starters.length})`}>
        <div className="card table-wrap">
          <SquadTable picks={data.squad} />
        </div>
      </Section>

      <AnalysisSections data={data} />

      <Legend
        items={[
          ["€m", "player price"],
          ["Opponent colour", "fixture difficulty 1 (green, easy) … 5 (red, hard) for the upcoming matchday"],
          ["Proj (horizon)", `projected points over the next ${data.horizon} matchdays`],
          ["Starter/Bench", "dimmed rows are the 4 bench players"],
        ]}
      />
      <p className="text-xs text-[var(--muted)]">
        Generated {dateTime(data.generatedAt)} (Mexico City time). Rebuilt on every sync — re-check right before the
        MD1 deadline.
      </p>
    </div>
  );
}

function AnalysisSections({ data }: { data: Output }) {
  const timing = data.matchdayTiming;
  const caps = data.captains;
  const chips = data.chips;
  return (
    <>
      {timing && timing.days > 1 && (
        <Section title="Matchday timing — bench decisions you can defer">
          <p className="text-sm text-[var(--muted)]">
            This matchday runs over {timing.days} days. You can still change your bench <em>after</em> the early games
            kick off, so lock in your day-1/2 nailed starters and keep high-upside day-{timing.days} players on the
            bench as live options — promote them only if you need the points after seeing the early results.
            {timing.liveOptions.length > 0 && (
              <>
                {" "}
                Live options this week: <b>{timing.liveOptions.join(", ")}</b>.
              </>
            )}
          </p>
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th className="num">Day</th>
                  <th>Pos</th>
                  <th>Player</th>
                  <th>Opponent</th>
                  <th className="num">xPts</th>
                  <th className="num hide-sm">Start%</th>
                </tr>
              </thead>
              <tbody>
                {timing.players.map((p) => (
                  <tr key={p.playerId}>
                    <td className="num">{p.mdDay ?? "–"}</td>
                    <td>
                      <PosBadge position={p.position} />
                    </td>
                    <td className="font-medium">{p.name}</td>
                    <OppCell {...p} />
                    <td className="num font-semibold">{fmt(p.xpts)}</td>
                    <td className="num hide-sm">{p.pStart != null ? `${Math.round(p.pStart * 100)}%` : "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}

      {caps && caps.candidates.length > 0 && (
        <Section title="Captain analysis (this matchday)">
          <p className="text-sm text-[var(--muted)]">
            Safe pick: <b>{caps.safePick?.name ?? "—"}</b>
            {caps.safePick && (
              <>
                {" "}
                (EV {fmt(caps.safePick.ev)}, floor {fmt(caps.safePick.floor)})
              </>
            )}
            {caps.differentialPick && (
              <>
                {" · "}Differential: <b>{caps.differentialPick.name}</b> (ceiling {fmt(caps.differentialPick.ceiling)},{" "}
                {fmt(caps.differentialPick.owned, 0)}% owned)
              </>
            )}
          </p>
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Player</th>
                  <th className="hide-sm">Team</th>
                  <th className="num">EV (2×)</th>
                  <th className="num">Ceiling</th>
                  <th className="num">Floor</th>
                  <th className="num hide-sm">Owned%</th>
                </tr>
              </thead>
              <tbody>
                {caps.candidates.map((c) => (
                  <tr key={c.playerId}>
                    <td className="font-medium">
                      {c.name}
                      {c.playerId === caps.safePick?.playerId && (
                        <span className="ml-1 text-[11px] font-semibold text-[var(--good)]">SAFE</span>
                      )}
                      {c.playerId === caps.differentialPick?.playerId && (
                        <span className="ml-1 text-[11px] font-semibold text-[var(--warn)]">DIFF</span>
                      )}
                    </td>
                    <td className="hide-sm">{c.team}</td>
                    <td className="num font-semibold">{fmt(c.ev)}</td>
                    <td className="num">{fmt(c.ceiling)}</td>
                    <td className="num">{fmt(c.floor)}</td>
                    <td className="num hide-sm">{fmt(c.owned, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}

      {data.matchdayPlan.length > 0 && (
        <Section title="Matchday-by-matchday plan">
          <p className="text-sm text-[var(--muted)]">
            How your squad projects each of the next {data.matchdayPlan.length} matchdays, and the best players to bring
            in <em>for that specific run</em> — target a transfer at whichever matchday opens up the biggest fixture
            swing.
          </p>
          <div className="space-y-4">
            {data.matchdayPlan.map((mp) => (
              <div key={mp.matchday} className="card p-3">
                <div className="mb-2 flex items-baseline justify-between">
                  <span className="font-semibold">MD{mp.matchday}</span>
                  <span className="text-sm text-[var(--muted)]">
                    projected XI + captain: <b>{fmt(mp.xiXpts, 0)}</b>
                  </span>
                </div>
                <div className="table-wrap">
                  <table className="dtable">
                    <thead>
                      <tr>
                        <th>Pos</th>
                        <th>Buy target</th>
                        <th>Team</th>
                        <th>Opponent</th>
                        <th className="num">€m</th>
                        <th className="num">xPts</th>
                      </tr>
                    </thead>
                    <tbody>
                      {mp.targets.map((p) => (
                        <tr key={p.playerId}>
                          <td>
                            <PosBadge position={p.position} />
                          </td>
                          <td className="font-medium">{p.name}</td>
                          <td>{p.team}</td>
                          <OppCell {...p} />
                          <td className="num">{fmt(p.price)}</td>
                          <td className="num font-semibold">{fmt(p.xpts)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </div>
        </Section>
      )}

      {chips && chips.perMatchday.length > 0 && (
        <Section title="Chip strategy">
          <div className="grid gap-3 sm:grid-cols-2">
            {(
              [
                ["limitless", "Limitless"],
                ["wildcard", "Wildcard"],
              ] as const
            ).map(([k, label]) => {
              const rec = chips.recommend[k];
              return (
                <div key={k} className="card p-3">
                  <div className="flex items-baseline justify-between">
                    <span className="font-semibold">{label}</span>
                    <span className="text-sm">
                      {rec ? (
                        <>
                          MD{rec.matchday} <span className="text-[var(--good)]">+{fmt(rec.gain)}</span>
                        </>
                      ) : (
                        <span className="text-[var(--muted)]">hold</span>
                      )}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-[var(--muted)]">
                    {rec?.why ??
                      (k === "limitless"
                        ? "Your squad can already field a competitive XI every matchday — no need."
                        : "No clear window yet.")}
                  </p>
                </div>
              );
            })}
          </div>
          <div className="card table-wrap mt-3">
            <table className="dtable">
              <thead>
                <tr>
                  <th className="num">MD</th>
                  <th className="num" title="best XI + captain your current 15 can field">XI now</th>
                  <th className="num" title="best XI + captain after spending your free transfers this matchday — the baseline Limitless is judged against">
                    XI w/ free transfers
                  </th>
                  <th className="num" title="best XI from the whole pool (price ignored) minus the free-transfer XI — one matchday only">
                    Limitless +
                  </th>
                  <th className="num" title="rebuild the squad and keep it — gain over the planning horizon (bigger scale than Limitless)">
                    Wildcard + (horizon)
                  </th>
                </tr>
              </thead>
              <tbody>
                {chips.perMatchday.map((m) => (
                  <tr key={m.matchday}>
                    <td className="num">{m.matchday}</td>
                    <td className="num">{fmt(m.currentXiXpts)}</td>
                    <td className="num">{fmt(m.freeTransferXiXpts ?? m.currentXiXpts)}</td>
                    <td className="num">{fmt(m.limitless)}</td>
                    <td className="num">{fmt(m.wildcard)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-[var(--muted)]">{chips.note}</p>
        </Section>
      )}
    </>
  );
}
