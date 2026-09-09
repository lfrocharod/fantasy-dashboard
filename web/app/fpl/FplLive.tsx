"use client";

import { useMemo } from "react";
import { LiveRefresher } from "@/components/LiveRefresher";
import { fmt } from "@/lib/format";
import type { DraftConfig } from "@/lib/draft/queries";
import type { FplPlayer } from "./lib";

/**
 * FPL Draft live gameweek: points banked so far, projected finish after FPL's
 * automatic substitutions, and your head-to-head score. (Draft has no captain,
 * so there's no armband or double here.) Written by the FPL sync
 * (`./draft.sh --sport fpl --sync`) while a GW is in progress.
 */

type Live = NonNullable<DraftConfig["fplLive"]>;
type Pick = DraftConfig["fplLineup"]["picks"][number];

const XI_MIN: Record<string, number> = { GKP: 1, DEF: 3, MID: 2, FWD: 1 };
const XI_MAX: Record<string, number> = { GKP: 1, DEF: 5, MID: 5, FWD: 1e9 };
const POS_COLOR: Record<string, string> = {
  GKP: "#6b7280", DEF: "#1f6feb", MID: "#1a7f37", FWD: "#cf222e",
};

function formationOk(c: Record<string, number>) {
  const n = Object.values(c).reduce((a, b) => a + b, 0);
  return n === 11 && Object.keys(XI_MIN).every((p) => (c[p] ?? 0) >= XI_MIN[p] && (c[p] ?? 0) <= XI_MAX[p]);
}

export function FplLive({
  live,
  squad,
  picks,
}: {
  live: Live;
  squad: FplPlayer[];
  picks: Pick[];
}) {
  const view = useMemo(() => {
    const byId = new Map(squad.map((p) => [p.extId, p]));
    const el = (id: string): [number, number] => live.elements[id] ?? [0, 0];
    const finished = live.state === "finished";

    const rows = picks
      .map((pk) => {
        const p = byId.get(pk.extId);
        if (!p) return null;
        const [pts, mins] = el(pk.extId);
        const projFallback = p.gws[0]?.xpts ?? p.proj;
        return {
          p,
          pts,
          mins,
          slot: pk.slot,
          starter: pk.starter,
          // definitely didn't play: GW over and never on the pitch
          dnp: finished && mins === 0,
          proj: mins > 0 || finished ? pts : projFallback,
          role: pk.starter ? "start" : "bench",
        };
      })
      .filter(Boolean) as {
      p: FplPlayer; pts: number; mins: number; slot: number; starter: boolean;
      dnp: boolean; proj: number; role: string;
    }[];

    const byRid = new Map(rows.map((r) => [r.p.extId, r]));
    const starters = rows.filter((r) => r.starter);
    const bench = rows.filter((r) => !r.starter).sort((a, b) => a.slot - b.slot);

    // FPL automatic substitutions (computed only once the GW is settled)
    const xi = new Set(starters.map((r) => r.p.extId));
    const counts: Record<string, number> = {};
    for (const r of starters) counts[r.p.pos] = (counts[r.p.pos] ?? 0) + 1;
    const autoSubs: { out: string; in: string }[] = [];
    const used = new Set<string>();
    if (finished) {
      for (const s of starters.filter((r) => r.dnp)) {
        for (const b of bench) {
          if (used.has(b.p.extId) || b.dnp) continue;
          if ((s.p.pos === "GKP") !== (b.p.pos === "GKP")) continue;
          const trial = { ...counts, [s.p.pos]: counts[s.p.pos] - 1, [b.p.pos]: (counts[b.p.pos] ?? 0) + 1 };
          if (!formationOk(trial)) continue;
          Object.assign(counts, trial);
          xi.delete(s.p.extId);
          xi.add(b.p.extId);
          used.add(b.p.extId);
          byRid.get(s.p.extId)!.role = "auto-out";
          byRid.get(b.p.extId)!.role = "auto-in";
          autoSubs.push({ out: s.p.name, in: b.p.name });
          break;
        }
      }
    }

    const effXi = [...xi].map((id) => byRid.get(id)!).filter(Boolean);
    const projectedFinish = effXi.reduce((a, r) => a + r.proj, 0);
    const notPlayed = starters.filter((r) => r.mins === 0 && !finished);

    const order = ["GKP", "DEF", "MID", "FWD"];
    const ordered = [...rows].sort(
      (a, b) =>
        (a.role === "auto-out" ? 2 : a.starter ? 0 : 1) - (b.role === "auto-out" ? 2 : b.starter ? 0 : 1) ||
        order.indexOf(a.p.pos) - order.indexOf(b.p.pos) ||
        b.proj - a.proj,
    );

    return { ordered, autoSubs, projectedFinish, notPlayed, starters, finished };
  }, [live, squad, picks]);

  const h2h = live.myPoints != null && live.oppName;
  const winning = h2h && (live.myPoints ?? 0) >= (live.oppPoints ?? 0);

  return (
    <section className="space-y-3">
      <LiveRefresher active={live.state === "live"} />
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">
          Live — GW{live.gw}
          <span className="ml-2 text-xs font-normal text-[var(--muted)]">
            {live.state === "finished" ? "settled" : "in progress"} · re-run the FPL sync to refresh
          </span>
        </h2>
      </div>

      {h2h && (
        <div
          className="card p-3 text-sm"
          style={{ borderLeft: `3px solid ${winning ? "var(--good)" : "var(--bad)"}` }}
        >
          <b>H2H GW{live.gw}:</b> you {live.myPoints} – {live.oppPoints} {live.oppName}{" "}
          <span style={{ color: winning ? "var(--good)" : "var(--bad)" }}>
            ({winning ? "ahead" : "behind"})
          </span>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="card p-3">
          <div className="text-xs text-[var(--muted)]">GW points</div>
          <div className="text-lg font-semibold">{live.secured}</div>
          <div className="text-xs text-[var(--muted)]">banked by your XI</div>
        </div>
        <div className="card p-3">
          <div className="text-xs text-[var(--muted)]">Projected finish</div>
          <div className="text-lg font-semibold">{fmt(view.projectedFinish, 0)}</div>
        </div>
        <div className="card p-3">
          <div className="text-xs text-[var(--muted)]">Played</div>
          <div className="text-lg font-semibold">
            {live.played}/{live.starters}
          </div>
        </div>
        <div className="card p-3">
          <div className="text-xs text-[var(--muted)]">Still to play</div>
          <div className="text-lg font-semibold">{view.notPlayed.length}</div>
        </div>
      </div>

      {view.autoSubs.length > 0 && (
        <div className="card space-y-1 p-3 text-sm">
          {view.autoSubs.map((s, i) => (
            <div key={i}>
              <b className="text-[var(--good)]">AUTO-SUB</b> {s.out} → <b>{s.in}</b>
            </div>
          ))}
        </div>
      )}

      {view.notPlayed.length > 0 && (
        <div className="card border-l-2 border-[var(--warn)] p-3 text-sm">
          Not started yet: {view.notPlayed.map((r) => r.p.name).join(", ")}
        </div>
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
            {view.ordered.map((r) => (
              <tr key={r.p.extId} style={r.role === "auto-out" ? { opacity: 0.5 } : undefined}>
                <td>
                  <span
                    className="rounded px-1 text-[10px] font-bold text-white"
                    style={{ background: POS_COLOR[r.p.pos] }}
                  >
                    {r.p.pos}
                  </span>
                </td>
                <td className="font-medium">
                  {r.p.name}
                  {r.role === "auto-in" && (
                    <span className="ml-1 text-[10px] font-semibold text-[var(--good)]">auto-sub in</span>
                  )}
                  {r.role === "auto-out" && (
                    <span className="ml-1 text-[10px] font-semibold text-[var(--bad)]">auto-sub out</span>
                  )}
                  {!r.starter && r.role === "bench" && (
                    <span className="ml-1 text-[10px] text-[var(--muted)]">bench</span>
                  )}
                </td>
                <td className="num">{r.mins || (r.dnp ? "0" : "–")}</td>
                <td className="num font-semibold">{r.mins > 0 || view.finished ? r.pts : "–"}</td>
                <td className="num text-[var(--muted)]">{view.finished ? "–" : fmt(r.proj, 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
