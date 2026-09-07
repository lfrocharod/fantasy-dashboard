import { EmptyState, Legend, PosBadge, StatCard, Section } from "@/components/ui";
import { fmt, dateTime } from "@/lib/format";
import { getSetting, KEYS } from "@/lib/settings";
import type { Position } from "@/lib/ucl/formation";

export const dynamic = "force-dynamic";

interface FixtureCtx {
  opp?: string | null;
  home?: boolean | null;
  fdr?: number | null;
}
interface OptPlayer extends FixtureCtx {
  playerId: number;
  name: string;
  team: string;
  position: Position;
  xpts: number;
  isCaptain?: boolean;
  isVice?: boolean;
  order?: number;
}

const FDR_BG: Record<number, string> = {
  1: "rgba(34,197,94,0.30)",
  2: "rgba(132,204,22,0.22)",
  3: "rgba(148,163,184,0.18)",
  4: "rgba(249,115,22,0.24)",
  5: "rgba(239,68,68,0.32)",
};

function OppCell({ opp, home, fdr }: FixtureCtx) {
  if (!opp) return <td className="text-[var(--muted)]">–</td>;
  return (
    <td style={fdr ? { background: FDR_BG[fdr] } : undefined} title={fdr ? `difficulty ${fdr}/5` : ""}>
      <span className="text-[var(--muted)]">{home ? "vs" : "@"}</span> {opp}
    </td>
  );
}
interface Transfer {
  out: OptPlayer;
  in: OptPlayer;
  horizonGain: number;
  hitCost: number;
  netGain: number;
}
interface SquadPick extends FixtureCtx {
  playerId: number;
  name: string;
  team: string;
  position: Position;
  price: number;
  horizonXpts: number;
  isStarter: boolean;
  isCaptain?: boolean;
  isVice?: boolean;
}
interface IdealSquad {
  matchday: number;
  horizon: number;
  formation: string;
  totalCost: number;
  budget: number;
  xiXpts: number;
  horizonXpts: number;
  squad: SquadPick[];
  changesFromCurrent?: number;
  keepFromCurrent?: number;
}
interface CaptainCand {
  playerId: number;
  name: string;
  team: string;
  position: Position;
  ev: number;
  ceiling: number;
  floor: number;
  owned: number;
}
interface CaptainAnalysis {
  candidates: CaptainCand[];
  safePick: CaptainCand | null;
  differentialPick: CaptainCand | null;
}
interface ChipMd {
  matchday: number;
  currentXiXpts: number;
  benchBoost: number;
  tripleCaptain: number;
  limitless: number;
  wildcard: number;
}
interface ChipEval {
  perMatchday: ChipMd[];
  recommend: Record<string, { matchday: number; gain: number } | null>;
  note: string;
}
interface PlanRow extends FixtureCtx {
  playerId: number;
  name: string;
  team: string;
  position: Position;
  price: number;
  xpts: number;
  owned: boolean;
}
interface MatchdayPlan {
  matchday: number;
  xiXpts: number;
  startForMd: PlanRow[];
  benchForMd: PlanRow[];
  targets: PlanRow[];
}
interface OptOutput {
  generatedAt: string;
  matchday: number;
  horizon: number;
  formation: string;
  baselineXpts: number;
  optimisedXpts: number;
  bestXI: OptPlayer[];
  bench: OptPlayer[];
  transfers: Transfer[];
  captains?: CaptainAnalysis;
  chips?: ChipEval;
  matchdayPlan?: MatchdayPlan[];
  preSeason?: boolean;
  freeTransfers?: number;
  idealSquad?: IdealSquad;
  totalCost?: number;
  budget?: number;
  xiXpts?: number;
  horizonXpts?: number;
  squad?: SquadPick[];
  changesFromCurrent?: number;
  keepFromCurrent?: number;
}

export default async function OptimizerPage() {
  const raw = await getSetting(KEYS.optimizerOutput);
  let data: OptOutput | null = null;
  try {
    data = raw ? (JSON.parse(raw) as OptOutput) : null;
  } catch {
    data = null;
  }

  if (!data) {
    return (
      <EmptyState
        title="No optimizer run yet"
        hint="The optimizer runs inside the ingestion job after projections are built. Run it, then refresh."
      />
    );
  }

  // Pre-season / no locked squad: the whole recommendation is a squad to build.
  if (data.preSeason && data.squad) {
    return <PreSeasonSquad data={data} />;
  }

  return (
    <div className="space-y-8">
      {data.idealSquad && (
        <Section title="If you wildcarded now">
          <p className="text-sm text-[var(--muted)]">
            Best possible 15 for the next {data.idealSquad.horizon} matchday(s) —{" "}
            <b>{data.idealSquad.changesFromCurrent}</b> changes from your current squad,
            €{fmt(data.idealSquad.totalCost)}m, projected {fmt(data.idealSquad.horizonXpts, 0)} pts.
          </p>
          <div className="card table-wrap">
            <SquadTable picks={data.idealSquad.squad} />
          </div>
        </Section>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="Formation" value={data.formation} />
        <StatCard label="Best XI xPts" value={fmt(data.optimisedXpts)} />
        <StatCard
          label="Gain vs current"
          value={`${data.optimisedXpts - data.baselineXpts >= 0 ? "+" : ""}${fmt(
            data.optimisedXpts - data.baselineXpts,
          )}`}
          sub="lineup only, no transfers"
        />
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
                  <OppCell opp={p.opp} home={p.home} fdr={p.fdr} />
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
                  <OppCell opp={p.opp} home={p.home} fdr={p.fdr} />
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
            No transfer improves your projected points over the next {data.horizon} matchday(s)
            once the –4 hit is accounted for. Roll the transfer.
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
                {data.transfers.map((t, i) => (
                  <tr key={i}>
                    <td>
                      {t.out.name} <span className="text-[var(--muted)]">({t.out.team})</span>
                    </td>
                    <td>
                      {t.in.name} <span className="text-[var(--muted)]">({t.in.team})</span>
                    </td>
                    <td className="num">{fmt(t.horizonGain)}</td>
                    <td className="num">{t.hitCost ? `-${t.hitCost}` : "0"}</td>
                    <td
                      className="num font-semibold"
                      style={{ color: t.netGain >= 0 ? "var(--good)" : "var(--bad)" }}
                    >
                      {t.netGain >= 0 ? "+" : ""}
                      {fmt(t.netGain)}
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
          ["Opponent colour", "fixture difficulty 1 (green, easy) … 5 (red, hard) for this matchday"],
          ["EV (2×)", "expected captain points = 2 × projected points"],
          ["Ceiling / Floor", "optimistic (p85) and pessimistic (p15) captain outcomes"],
          ["Bench Boost / Triple Capt / Limitless / Wildcard", "extra points if that chip is played that matchday (estimated)"],
          ["Δ xPts", `total xPts gained over the next ${data.horizon} matchday(s)`],
          ["Hit", "points cost of an extra transfer (−4 each beyond the free one)"],
          ["Net", "Δ xPts minus the hit — only make the move if this is clearly positive"],
          ["(C)/(V)", "captain / vice-captain"],
        ]}
      />
      <p className="text-xs text-[var(--muted)]">
        Generated {dateTime(data.generatedAt)} for matchday {data.matchday} (Mexico City time).
      </p>
    </div>
  );
}

const POS_ORDER = ["GK", "DEF", "MID", "FWD"] as const;

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
            <OppCell opp={p.opp} home={p.home} fdr={p.fdr} />
            <td className="num">{fmt(p.price)}</td>
            <td className="num font-semibold">{fmt(p.horizonXpts, 0)}</td>
            <td>
              {p.isCaptain ? "Captain" : p.isVice ? "Vice" : p.isStarter ? "Starter" : "Bench"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function PreSeasonSquad({ data }: { data: OptOutput }) {
  const picks = data.squad ?? [];
  const starters = picks.filter((p) => p.isStarter);
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Recommended squad to start the season</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Best legal 15 within €{fmt(data.budget ?? 100)}m, 2·5·5·3 and max 3 per club,
          maximising projected points over the next {data.horizon} matchday(s). Your team
          isn’t locked until the first MD1 match kicks off, so you can build this for free.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="Formation" value={data.formation} />
        <StatCard label="Squad cost" value={`€${fmt(data.totalCost ?? 0)}m`} sub={`of €${fmt(data.budget ?? 100)}m`} />
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
          <SquadTable picks={picks} />
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
        Generated {dateTime(data.generatedAt)} (Mexico City time). Rebuilds every ingestion run —
        re-check right before the MD1 deadline.
      </p>
    </div>
  );
}

function AnalysisSections({ data }: { data: OptOutput }) {
  return (
    <>
      {data.captains && data.captains.candidates.length > 0 && (
        <Section title="Captain analysis (this matchday)">
          <p className="text-sm text-[var(--muted)]">
            Safe pick:{" "}
            <b>{data.captains.safePick?.name ?? "—"}</b>
            {data.captains.safePick && (
              <> (EV {fmt(data.captains.safePick.ev)}, floor {fmt(data.captains.safePick.floor)})</>
            )}
            {data.captains.differentialPick && (
              <>
                {" · "}Differential: <b>{data.captains.differentialPick.name}</b> (ceiling{" "}
                {fmt(data.captains.differentialPick.ceiling)}, {fmt(data.captains.differentialPick.owned, 0)}% owned)
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
                {data.captains.candidates.map((c) => (
                  <tr key={c.playerId}>
                    <td className="font-medium">
                      {c.name}
                      {c.playerId === data.captains?.safePick?.playerId && (
                        <span className="ml-1 text-[11px] font-semibold text-[var(--good)]">SAFE</span>
                      )}
                      {c.playerId === data.captains?.differentialPick?.playerId && (
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

      {data.matchdayPlan && data.matchdayPlan.length > 0 && (
        <Section title="Matchday-by-matchday plan">
          <p className="text-sm text-[var(--muted)]">
            How your squad projects each of the next {data.matchdayPlan.length} matchdays, and the
            best players to bring in <em>for that specific run</em> — target a transfer at whichever
            matchday opens up the biggest fixture swing.
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
                          <OppCell opp={p.opp} home={p.home} fdr={p.fdr} />
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

      {data.chips && data.chips.perMatchday.length > 0 && (
        <Section title="Chip strategy">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {(
              [
                ["wildcard", "Wildcard"],
                ["limitless", "Limitless"],
                ["benchBoost", "Bench Boost"],
                ["tripleCaptain", "Triple Captain"],
              ] as const
            ).map(([k, label]) => {
              const rec = data.chips?.recommend[k];
              return (
                <StatCard
                  key={k}
                  label={label}
                  value={rec ? `MD${rec.matchday}` : "—"}
                  sub={rec ? `+${fmt(rec.gain)} pts` : "no clear gain"}
                />
              );
            })}
          </div>
          <div className="card table-wrap mt-3">
            <table className="dtable">
              <thead>
                <tr>
                  <th className="num">MD</th>
                  <th className="num">XI now</th>
                  <th className="num">Bench Boost</th>
                  <th className="num">Triple Capt</th>
                  <th className="num">Limitless</th>
                  <th className="num">Wildcard</th>
                </tr>
              </thead>
              <tbody>
                {data.chips.perMatchday.map((m) => (
                  <tr key={m.matchday}>
                    <td className="num">{m.matchday}</td>
                    <td className="num">{fmt(m.currentXiXpts)}</td>
                    <td className="num">{fmt(m.benchBoost)}</td>
                    <td className="num">{fmt(m.tripleCaptain)}</td>
                    <td className="num">{fmt(m.limitless)}</td>
                    <td className="num">{fmt(m.wildcard)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-[var(--muted)]">{data.chips.note}</p>
        </Section>
      )}
    </>
  );
}
