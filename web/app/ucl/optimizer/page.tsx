import { EmptyState, PosBadge, StatCard, Section } from "@/components/ui";
import { fmt } from "@/lib/format";
import { getSetting, KEYS } from "@/lib/settings";
import type { Position } from "@/lib/ucl/formation";

export const dynamic = "force-dynamic";

interface OptPlayer {
  playerId: number;
  name: string;
  team: string;
  position: Position;
  xpts: number;
  isCaptain?: boolean;
  isVice?: boolean;
  order?: number;
}
interface Transfer {
  out: OptPlayer;
  in: OptPlayer;
  horizonGain: number;
  hitCost: number;
  netGain: number;
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

  return (
    <div className="space-y-8">
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
        <div className="card overflow-x-auto">
          <table className="grid">
            <thead>
              <tr>
                <th>Pos</th>
                <th>Player</th>
                <th>Team</th>
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
                  <td className="num font-semibold">{fmt(p.xpts)}</td>
                  <td>{p.isCaptain ? "(C)" : p.isVice ? "(V)" : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="Bench order">
        <div className="card overflow-x-auto">
          <table className="grid">
            <thead>
              <tr>
                <th>#</th>
                <th>Pos</th>
                <th>Player</th>
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
          <div className="card overflow-x-auto">
            <table className="grid">
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

      <p className="text-xs text-[var(--muted)]">
        Generated {new Date(data.generatedAt).toLocaleString()} for matchday {data.matchday}.
      </p>
    </div>
  );
}
