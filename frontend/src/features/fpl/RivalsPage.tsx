import { useState } from "react";
import { $api, type Api } from "@/api/client";
import { fmt } from "@/shared/format";
import { EmptyState, Legend, PosBadge, QueryView, SubHeading, Toggle } from "@/shared/ui";
import type { Player } from "./common";

type Metric = "medium" | "season";
const POS_ORDER = ["GKP", "DEF", "MID", "FWD"];

export default function FplRivalsPage() {
  const q = $api.useQuery("get", "/api/fpl/rivals");
  return <QueryView query={q}>{(d) => <Rivals d={d} />}</QueryView>;
}

function Rivals({ d }: { d: Api["FplRivalsResponse"] }) {
  const [metric, setMetric] = useState<Metric>("season");
  if (d.managers.length === 0) {
    return <EmptyState title="No roster data yet" hint="The next FPL sync pulls every manager's squad." />;
  }
  const v = (p: Player) => (metric === "medium" ? p.horizon : p.ros);
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">Rivals</h1>
        <span className="text-sm text-[var(--muted)]">
          Your projected next GW: <strong>{fmt(d.myProj, 0)}</strong>
        </span>
        <div className="ml-auto">
          <Toggle value={metric} options={[["medium", "next 6 GW"], ["season", "rest of season"]] as const} onChange={setMetric} />
        </div>
      </div>

      {d.rivals.length > 0 && (
        <section className="space-y-2">
          <SubHeading>Rivals — projected next GW</SubHeading>
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Manager</th>
                  <th className="num">Proj GW</th>
                  <th className="num">vs you</th>
                  <th className="hide-sm">Their edge (they have, you don't)</th>
                </tr>
              </thead>
              <tbody>
                {d.rivals.map((r) => (
                  <tr key={r.entryId}>
                    <td className="font-medium">{r.name}</td>
                    <td className="num font-semibold">{fmt(r.proj, 0)}</td>
                    <td className="num font-semibold" style={{ color: r.proj > d.myProj ? "var(--bad)" : "var(--good)" }}>
                      {r.proj > d.myProj ? "+" : ""}
                      {fmt(r.proj - d.myProj, 0)}
                    </td>
                    <td className="hide-sm text-xs text-[var(--muted)]">
                      {r.diffs.map((p) => `${p.name} (${fmt(v(p), 0)})`).join(", ") || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {d.claims.length > 0 && (
        <section className="space-y-2">
          <SubHeading>Likely rival waiver claims — get there first</SubHeading>
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Rival</th>
                  <th>Weak spot</th>
                  <th>Likely target</th>
                  <th className="num">Their gain</th>
                </tr>
              </thead>
              <tbody>
                {d.claims.map((c) => (
                  <tr key={`${c.rivalName}-${c.target.extId}`}>
                    <td>{c.rivalName}</td>
                    <td className="text-[var(--muted)]">
                      {c.weakPos} · {c.weakStarter}
                    </td>
                    <td className="font-medium">
                      {c.target.name} <span className="text-[var(--muted)]">{c.target.team}</span>
                    </td>
                    <td className="num font-semibold">+{fmt(c.gain, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {d.effectiveOwnership.length > 0 && (
        <section className="space-y-2">
          <SubHeading>Effective ownership — in your league only</SubHeading>
          <p className="text-sm text-[var(--muted)]">
            What matters is how many of the {d.leagueSize} managers you're racing own each player. Low % + high ROS = a
            real advantage if you can get them; high % = neutral.
          </p>
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Player</th>
                  <th>Team</th>
                  <th className="num">Owned</th>
                  <th className="num">ROS</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {d.effectiveOwnership.map((e) => (
                  <tr key={e.player.extId} style={e.mine ? { background: "rgba(31,111,235,0.08)" } : undefined}>
                    <td className="font-medium">{e.player.name}</td>
                    <td className="text-[var(--muted)]">{e.player.team}</td>
                    <td className="num font-semibold" style={{ color: e.pct >= 60 ? "var(--muted)" : e.pct <= 34 ? "var(--good)" : undefined }}>
                      {e.pct}%
                    </td>
                    <td className="num">{fmt(e.player.ros, 0)}</td>
                    <td className="text-xs">
                      {e.mine ? (
                        <span className="text-[var(--accent)]">you</span>
                      ) : e.player.available ? (
                        <span className="text-[var(--good)]">free agent</span>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="space-y-2">
        <SubHeading>Manager rosters</SubHeading>
        <div className="grid gap-4 lg:grid-cols-2">
          {d.managers.map((mg) => (
            <ManagerCard key={mg.entryId} mg={mg} total={metric === "medium" ? mg.totalMedium : mg.totalSeason} v={v} />
          ))}
        </div>
      </section>

      <Legend
        items={[
          ["Proj GW", "their best legal XI's projected points next gameweek"],
          ["vs you", "their projection minus yours — red means they out-project you"],
          ["Their edge", "players they own that you don't — where they can gain on you"],
          ["Owned", "share of your league that holds this player"],
          ["value", `projected draft points — ${metric === "medium" ? "next 6 GW" : "rest of season"}`],
          ["⚑", "one booking from a suspension"],
        ]}
      />
    </div>
  );
}

function ManagerCard({ mg, total, v }: { mg: Api["Manager"]; total: number; v: (p: Player) => number }) {
  return (
    <div className={`card p-3 ${mg.isMine ? "ring-1 ring-[var(--accent)]" : ""}`}>
      <div className="mb-2 flex items-baseline justify-between">
        <span className="font-semibold">
          {mg.name} {mg.isMine && <span className="text-xs text-[var(--accent)]">(you)</span>}
        </span>
        <span className="text-sm text-[var(--muted)]">Σ {fmt(total, 0)}</span>
      </div>
      <div className="table-wrap">
        <table className="dtable text-xs">
          <tbody>
            {POS_ORDER.flatMap((pos) => {
              const list = mg.byPos[pos] ?? [];
              return list.map((p, i) => (
                <tr key={p.extId}>
                  {i === 0 && (
                    <td rowSpan={list.length} className="align-top">
                      <PosBadge position={pos} small />
                    </td>
                  )}
                  <td className="font-medium">
                    {p.name}
                    {p.suspRisk && (
                      <span className="ml-1 text-[var(--warn)]" title={`${p.ycToBan} booking from a ban`}>
                        ⚑
                      </span>
                    )}
                    {p.unavailable && (
                      <span className="ml-1 text-[10px] text-[var(--bad)]">
                        {p.status === "s" ? "susp" : p.status === "i" ? "inj" : "doubt"}
                      </span>
                    )}
                  </td>
                  <td className="text-[var(--muted)]">
                    {p.team}
                    {p.nextOpp && <span className="ml-1 opacity-70">· {p.nextOpp}</span>}
                  </td>
                  <td className="num font-semibold">{fmt(v(p), 0)}</td>
                </tr>
              ));
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
