import { useState } from "react";
import { $api, type Api } from "@/api/client";
import { FDR_BG } from "@/shared/fdr";
import { fmt } from "@/shared/format";
import { EmptyState, Legend, PosBadge, QueryView, SubHeading, Toggle } from "@/shared/ui";
import { Flags, HORIZON_LABEL, HORIZONS, type Horizon, type Player } from "./common";

const POS = ["ALL", "GKP", "DEF", "MID", "FWD"] as const;
type Pos = (typeof POS)[number];

export default function FplOptimizerPage() {
  const [horizon, setHorizon] = useState<Horizon>("medium");
  const q = $api.useQuery("get", "/api/fpl/optimizer", { params: { query: { horizon } } }, {
    placeholderData: (prev) => prev, // keep the page while a new horizon loads
  });
  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Optimizer</h1>
      <QueryView query={q}>{(d) => <Optimizer d={d} horizon={horizon} setHorizon={setHorizon} />}</QueryView>
    </div>
  );
}

function Optimizer({ d, horizon, setHorizon }: { d: Api["FplOptimizerResponse"]; horizon: Horizon; setHorizon: (h: Horizon) => void }) {
  const [mode, setMode] = useState<"squad" | "targets">("squad");
  const [pos, setPos] = useState<Pos>("ALL");
  if (d.gws.length === 0) return <EmptyState title="No projections yet" hint="Waiting for the first FPL sync." />;
  const rows = mode === "squad" ? d.squad : (d.targets[pos] ?? []);
  return (
    <>
      <section className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <SubHeading>Rotation planner</SubHeading>
          <div className="ml-auto">
            <Toggle value={mode} options={[["squad", "My squad"], ["targets", "Free-agent targets"]] as const} onChange={setMode} />
          </div>
        </div>
        {mode === "targets" && <Toggle value={pos} options={POS} onChange={setPos} />}
        <div className="card table-wrap">
          <table className="dtable text-xs">
            <thead>
              <tr>
                <th className="sticky left-0 bg-[var(--surface)]">Player</th>
                {d.gws.map((g) => (
                  <th key={g} className="num">GW{g}</th>
                ))}
                <th className="num">Σ{d.gws.length}</th>
                <th className="num hide-sm">CS%</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <MatrixRow key={p.extId} p={p} />
              ))}
            </tbody>
            {mode === "squad" && d.bestXiTotals.length > 0 && (
              <tfoot>
                <tr className="border-t border-[var(--border)] font-semibold">
                  <td className="sticky left-0 bg-[var(--surface)]">Best XI total</td>
                  {d.bestXiTotals.map((t, i) => (
                    <td key={d.gws[i]} className="num">{fmt(t, 0)}</td>
                  ))}
                  <td className="num">{fmt(d.bestXiHorizon, 0)}</td>
                  <td className="hide-sm" />
                </tr>
              </tfoot>
            )}
          </table>
        </div>
        <p className="text-xs text-[var(--muted)]">
          <b>Cell colour = fixture difficulty</b> (green easy → red hard); the number is that player's projected
          points. Σ is the sum over the shown gameweeks. The footer is your best legal XI total per GW (no captaincy in
          draft) — watch it for the weeks a waiver or trade buys you the most.
        </p>
      </section>

      <section className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <SubHeading>Waiver claims</SubHeading>
          <div className="ml-auto">
            <Toggle value={horizon} options={HORIZONS} label={(h) => HORIZON_LABEL[h]} onChange={setHorizon} />
          </div>
        </div>
        {d.upgrades.length === 0 ? (
          <p className="text-sm text-[var(--muted)]">
            No free agent clearly improves your XI over the {HORIZON_LABEL[horizon]} window.
          </p>
        ) : (
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Drop</th>
                  <th>Claim</th>
                  <th className="num hide-sm">Next</th>
                  <th className="num">+ pts</th>
                </tr>
              </thead>
              <tbody>
                {d.upgrades.map((u) => (
                  <tr key={u.in.extId}>
                    <td>
                      {u.out.name} <span className="text-[var(--muted)]">({fmt(u.outValue, 0)})</span>
                    </td>
                    <td className="font-medium">
                      {u.in.name}{" "}
                      <span className="text-[var(--muted)]">
                        {u.in.team} · {u.in.nextOpp}
                      </span>
                      {u.in.suspRisk && (
                        <span className="ml-1 text-[var(--warn)]" title={`${u.in.ycToBan} booking from a ban`}>
                          ⚑
                        </span>
                      )}
                    </td>
                    <td className="num hide-sm">{fmt(u.in.proj)}</td>
                    <td className="num font-semibold text-[var(--good)]">+{fmt(u.gain, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="text-xs text-[var(--muted)]">
          {horizon === "short"
            ? "Short-term: just needs to feature this week — suspension risk doesn't matter."
            : "Medium/long: fit, nailed starters only, and players a booking from a ban are excluded."}
        </p>
      </section>

      {d.stash.length > 0 && (
        <section className="space-y-2">
          <SubHeading>Stash &amp; wait (injured, but worth a roster spot)</SubHeading>
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Player</th>
                  <th className="hide-sm">News</th>
                  <th className="num">When fit</th>
                  <th className="num hide-sm">Total pts</th>
                </tr>
              </thead>
              <tbody>
                {d.stash.map((p) => (
                  <tr key={p.extId}>
                    <td className="font-medium">
                      {p.name} <span className="text-[var(--muted)]">{p.team}</span>
                    </td>
                    <td className="hide-sm text-xs text-[var(--muted)]">{p.news || p.status}</td>
                    <td className="num font-semibold">{fmt(p.fitNext)}</td>
                    <td className="num hide-sm">{p.totalPoints}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <Legend
        items={[
          ["Matrix cell", "colour = fixture difficulty (green easy … red hard); number = projected points"],
          ["Σ", "sum of projected points over the shown gameweeks"],
          ["CS%", "clean-sheet probability (opponent attack vs your team's defence)"],
          ["+ pts", "projected gain over the player you'd drop, across the selected window"],
          ["When fit", "projected next-GW output once the injury clears"],
        ]}
      />
    </>
  );
}

function MatrixRow({ p }: { p: Player }) {
  return (
    <tr>
      <td className="sticky left-0 whitespace-nowrap bg-[var(--surface)] font-medium">
        <span className="mr-1">
          <PosBadge position={p.pos} small />
        </span>
        {p.name}
        <Flags p={p} />
      </td>
      {p.gws.map((g) => (
        <td key={g.gw} className="num" style={{ background: g.opp ? (FDR_BG[g.fdr] ?? "transparent") : "transparent" }}
          title={g.opp ? `${g.opp} · difficulty ${g.fdr}/5 · proj ${fmt(g.xpts)}` : "no fixture"}>
          <div className="font-semibold">{g.opp ? fmt(g.xpts) : "–"}</div>
          <div className="text-[9px] text-[var(--muted)]">{g.opp.replace(/ \(/g, "(")}</div>
        </td>
      ))}
      <td className="num font-semibold">{fmt(p.horizon, 0)}</td>
      <td className="num hide-sm">{p.pos === "FWD" ? "–" : Math.round(p.csProb * 100)}</td>
    </tr>
  );
}
