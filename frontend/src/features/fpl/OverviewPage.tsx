import { useState } from "react";
import { $api, type Api } from "@/api/client";
import { DraftSetup } from "@/features/draft/DraftSetup";
import { FDR_BG, FDR_TEXT } from "@/shared/fdr";
import { fmt } from "@/shared/format";
import { Checklist, Legend, PosBadge, QueryView, StatCard, SubHeading } from "@/shared/ui";
import { clamp5, Flags, GwTd, startPct } from "./common";

export default function FplOverviewPage() {
  const q = $api.useQuery("get", "/api/fpl/overview", {}, {
    refetchInterval: (query) => (query.state.data?.live?.state === "live" ? 60_000 : false),
  });
  const [setup, setSetup] = useState(false);
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">
          FPL Draft
          {q.data && (
            <>
              {` — ${q.data.teams}-team league`}
              {q.data.gws.length > 0 && ` · GW${q.data.gws[0]}–${q.data.gws.at(-1)}`}
            </>
          )}
        </h1>
        <button type="button" className="btn" onClick={() => setSetup((v) => !v)}>
          {setup ? "Close" : "Setup"}
        </button>
      </div>
      {setup && <DraftSetup sport="fpl" />}
      <QueryView query={q}>{(o) => <Overview o={o} />}</QueryView>
    </div>
  );
}

function Overview({ o }: { o: Api["FplOverview"] }) {
  if (!o.hasSquad) {
    return (
      <p className="card p-3 text-sm text-[var(--muted)]">
        Add your league ID + entry ID in Setup (no login token needed) — the next scheduled sync pulls your squad.
      </p>
    );
  }
  return (
    <>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="Next GW" value={`GW${o.nextGw || "?"}`} />
        <StatCard label="Your XI proj" value={fmt(o.nextGwProj, 0)} sub={o.fromApp ? o.formation : "model best XI"} />
        <StatCard label="Squad ROS / GW" value={fmt(o.rosPerGw, 1)} />
        <StatCard label="League rank" value={o.myRank ?? "–"} sub={o.leagueSize ? `of ${o.leagueSize}` : undefined} />
      </div>

      {o.live && <FplLive live={o.live} />}

      {o.swaps.length > 0 && (
        <div className="card border-l-2 border-[var(--warn)] p-3 text-sm">
          <b className="text-[var(--warn)]">Bench call vs your set XI:</b>
          <ul className="mt-1 space-y-0.5">
            {o.swaps.map((s) => (
              <li key={s.out.extId}>
                Start <b>{s.in.name}</b> for {s.out.name} <span className="text-[var(--good)]">(+{fmt(s.gain)} proj)</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <section className="space-y-2">
        <SubHeading>Pre-deadline checklist</SubHeading>
        <Checklist items={o.checklist} />
      </section>

      <section className="space-y-2">
        <SubHeading>
          Your squad{" "}
          {o.fromApp && (
            <span className="font-normal normal-case">
              · {o.lineupSource === "my-team" ? "live Pick Team" : "last fielded XI"} ({o.formation})
            </span>
          )}
        </SubHeading>
        <div className="card table-wrap">
          <table className="dtable">
            <thead>
              <tr>
                <th>Pos</th>
                <th>Player</th>
                <th>Team</th>
                <th>Opp (GW{o.nextGw || "?"})</th>
                <th className="num">Start%</th>
                <th className="num">Next</th>
                <th className="num">ROS</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {o.squad.map(({ player: p, starting }) => {
                const g = p.gws[0];
                return (
                  <tr key={p.extId} style={starting ? undefined : { opacity: 0.55 }}>
                    <td>
                      <PosBadge position={p.pos} small />
                    </td>
                    <td className="font-medium">
                      {p.name}
                      <Flags p={p} />
                    </td>
                    <td className="text-[var(--muted)]">{p.team}</td>
                    <td className="font-medium" style={{ color: g?.opp ? (FDR_TEXT[g.fdr] ?? "var(--muted)") : "var(--muted)" }}
                      title={g?.opp ? `${p.pos} difficulty ${g.fdr}/5${g.fdrAtt ? ` — goals/assists ${g.fdrAtt}/5, clean sheet ${g.fdrDef}/5` : ""}` : "no fixture"}>
                      {g?.opp || "–"}
                    </td>
                    <td className="num">{startPct(p.pStart)}</td>
                    <td className="num font-semibold">{fmt(p.proj)}</td>
                    <td className="num">{fmt(p.ros, 0)}</td>
                    <td className="text-[10px] text-[var(--muted)]">{starting ? "XI" : "bench"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {o.fixtureRun && <FixtureRun run={o.fixtureRun} />}

      {o.modelCheck.length > 0 && <ModelCheck rows={o.modelCheck} />}

      <Legend
        items={[
          ["XI / bench", o.fromApp
            ? "your actual FPL lineup (live Pick Team with the login token, otherwise your last fielded XI)"
            : "the model's best legal XI (no saved lineup pulled yet)"],
          ["Opp colour", "position-aware fixture difficulty (green easy … red hard): forwards weigh the opponent's defensive solidity, keepers their attacking threat, defenders mostly clean-sheet risk plus some set-piece upside, midfielders mostly attacking"],
          ["Start%", "modelled chance of starting the next match"],
          ["Next / ROS", "projected draft points next GW / rest of season"],
          ["⚑", "one booking from a suspension"],
        ]}
      />
    </>
  );
}

/** Live gameweek: points banked, projected finish after FPL's automatic
 * substitutions, and the head-to-head score. Draft has no captain. */
function FplLive({ live }: { live: Api["FplLiveView"] }) {
  const finished = live.state === "finished";
  const h2h = live.myPoints != null && live.oppName;
  const winning = h2h && (live.myPoints ?? 0) >= (live.oppPoints ?? 0);
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">
        Live — GW{live.gw}
        <span className="ml-2 text-xs font-normal text-[var(--muted)]">
          {finished ? "settled" : "in progress · updates with each sync"}
        </span>
      </h2>
      {h2h && (
        <div className="card p-3 text-sm" style={{ borderLeft: `3px solid ${winning ? "var(--good)" : "var(--bad)"}` }}>
          <b>H2H GW{live.gw}:</b> you {live.myPoints} – {live.oppPoints} {live.oppName}{" "}
          <span style={{ color: winning ? "var(--good)" : "var(--bad)" }}>({winning ? "ahead" : "behind"})</span>
        </div>
      )}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="GW points" value={live.secured} sub="banked by your XI" />
        <StatCard label="Projected finish" value={fmt(live.projectedFinish, 0)} />
        <StatCard label="Played" value={`${live.played}/${live.starters}`} />
        <StatCard label="Still to play" value={live.notPlayed.length} />
      </div>
      {live.autoSubs.length > 0 && (
        <div className="card space-y-1 p-3 text-sm">
          {live.autoSubs.map((s) => (
            <div key={s.out}>
              <b className="text-[var(--good)]">AUTO-SUB</b> {s.out} → <b>{s.in}</b>
            </div>
          ))}
        </div>
      )}
      {live.notPlayed.length > 0 && (
        <div className="card border-l-2 border-[var(--warn)] p-3 text-sm">Not started yet: {live.notPlayed.join(", ")}</div>
      )}
      <div className="card table-wrap">
        <table className="dtable">
          <thead>
            <tr>
              <th>Pos</th>
              <th>Player</th>
              <th className="num">Min</th>
              <th className="num">Pts</th>
              <th className="num">Proj</th>
            </tr>
          </thead>
          <tbody>
            {live.rows.map((r) => (
              <tr key={r.player.extId} style={r.role === "auto-out" ? { opacity: 0.5 } : undefined}>
                <td>
                  <PosBadge position={r.player.pos} small />
                </td>
                <td className="font-medium">
                  {r.player.name}
                  {r.role === "auto-in" && <span className="ml-1 text-[10px] font-semibold text-[var(--good)]">auto-sub in</span>}
                  {r.role === "auto-out" && <span className="ml-1 text-[10px] font-semibold text-[var(--bad)]">auto-sub out</span>}
                  {r.role === "bench" && <span className="ml-1 text-[10px] text-[var(--muted)]">bench</span>}
                </td>
                <td className="num">{r.minutes || (r.dnp ? "0" : "–")}</td>
                <td className="num font-semibold">{r.minutes > 0 || finished ? r.points : "–"}</td>
                <td className="num text-[var(--muted)]">{finished ? "–" : fmt(r.proj, 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/** The squad's schedule swing: a squad-average strip on top (which GWs are a
 * wall), then each player's own run, easiest first. */
function FixtureRun({ run }: { run: Api["FixtureRun"] }) {
  return (
    <section className="space-y-2">
      <SubHeading>Your fixture run — next {run.gws.length} GW</SubHeading>
      <div className="card table-wrap">
        <table className="dtable">
          <thead>
            <tr>
              <th>Player</th>
              {run.gws.map((g) => (
                <th key={g} className="num">GW{g}</th>
              ))}
              <th className="num">Avg</th>
            </tr>
          </thead>
          <tbody>
            <tr className="font-semibold">
              <td className="text-[var(--muted)]">Squad avg</td>
              {run.colMean.map((m, i) => (
                <td key={run.gws[i]} className="num tabular-nums" style={m ? { background: FDR_BG[clamp5(m)] } : undefined}>
                  {m ? fmt(m, 1) : "–"}
                </td>
              ))}
              <td className="num">{fmt(run.overall, 1)}</td>
            </tr>
            {run.rows.map(({ player: p, cells, mean }) => (
              <tr key={p.extId}>
                <td className="font-medium">
                  {p.name} <span className="text-[var(--muted)]">{p.team}</span>
                </td>
                {run.gws.map((gw) => (
                  <GwTd key={gw} c={cells.find((c) => c.gw === gw)} />
                ))}
                <td className="num font-semibold" style={{ background: FDR_BG[clamp5(mean)] }}>
                  {fmt(mean, 1)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-[var(--muted)]">
        Difficulty is position-aware (a defender's number weighs clean-sheet risk, an attacker's the opponent's
        defence). Green = easy run, red = wall.
      </p>
    </section>
  );
}

const REPORT = "https://github.com/lfrocharod/fantasy-dashboard/blob/main/docs/ml/fpl-backtest.md";

/** How each model's pre-deadline projection compared with what happened. */
function ModelCheck({ rows }: { rows: Api["ModelCheckRow"][] }) {
  const cell = (v: number | null, best: number) => (
    <td className="num" style={v != null && v === best ? { color: "var(--good)", fontWeight: 600 } : undefined}>
      {fmt(v, 2)}
    </td>
  );
  return (
    <section className="space-y-2">
      <SubHeading>Model check — error per gameweek</SubHeading>
      <div className="card table-wrap">
        <table className="dtable">
          <thead>
            <tr>
              <th>GW</th>
              <th className="num">Players</th>
              <th className="num" title="gradient-boosted trees on public FPL history">ML</th>
              <th className="num" title="the minutes × fixture model behind xPts">Structural</th>
              <th className="num" title="FPL's own expected points (ep_next)">FPL</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const best = Math.min(...[r.ml, r.structural, r.fplEp].filter((v): v is number => v != null));
              return (
                <tr key={r.round}>
                  <td>GW{r.round}</td>
                  <td className="num text-[var(--muted)]">{r.n}</td>
                  {cell(r.ml, best)}
                  {cell(r.structural, best)}
                  {cell(r.fplEp, best)}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-[var(--muted)]">
        Mean absolute error in points over the players any model projected for 2+, from predictions stored before each
        deadline; lowest is green. How the ML model was built and backtested:{" "}
        <a href={REPORT} className="text-[var(--accent)]" target="_blank" rel="noreferrer">
          backtest report
        </a>
        .
      </p>
    </section>
  );
}
