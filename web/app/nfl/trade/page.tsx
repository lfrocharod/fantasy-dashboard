"use client";

import { useEffect, useMemo, useState } from "react";
import { Legend } from "@/components/ui";
import { fmt } from "@/lib/format";
import type { DraftConfig } from "@/lib/draft/queries";
import { OUT_STATUS, POS_COLOR, groupTeams, loadNfl, type NflPlayer } from "../lib";

function Chip({ p, on, toggle }: { p: NflPlayer; on: boolean; toggle: () => void }) {
  return (
    <button
      onClick={toggle}
      className={`m-0.5 rounded border px-1.5 py-0.5 text-xs ${
        on ? "border-[var(--accent)] bg-[var(--accent)] text-white" : "border-[var(--border)]"
      }`}
      title={`wk ${fmt(p.weekProj)} · ROS ${fmt(p.rosProj, 0)}`}
    >
      <span className="mr-1 rounded px-0.5 text-[9px] font-bold text-white" style={{ background: POS_COLOR[p.pos] }}>
        {p.pos}
      </span>
      {p.name}
      {OUT_STATUS.has(p.injury) && <span className="ml-0.5 text-[var(--bad)]">✚</span>}
    </button>
  );
}

export default function NflTradePage() {
  const [players, setPlayers] = useState<NflPlayer[]>([]);
  const [config, setConfig] = useState<DraftConfig | null>(null);
  const [rival, setRival] = useState<number | null>(null);
  const [give, setGive] = useState<Set<string>>(new Set());
  const [get, setGet] = useState<Set<string>>(new Set());

  useEffect(() => {
    loadNfl().then((d) => {
      setPlayers(d.players);
      setConfig(d.config);
    });
  }, []);

  const teams = useMemo(() => groupTeams(players, config?.myTeamId ?? null), [players, config]);
  const me = teams.find((t) => t.isMine);
  const rivals = teams.filter((t) => !t.isMine);
  const their = rivals.find((t) => t.teamId === rival) ?? rivals[0];
  const byId = useMemo(() => new Map(players.map((p) => [p.extId, p])), [players]);

  const giveP = [...give].map((id) => byId.get(id)!).filter(Boolean);
  const getP = [...get].map((id) => byId.get(id)!).filter(Boolean);

  const evalTrade = useMemo(() => {
    if (!giveP.length && !getP.length) return null;
    const sum = (a: NflPlayer[], f: (p: NflPlayer) => number) => a.reduce((x, p) => x + f(p), 0);
    const meWeek = sum(getP, (p) => p.weekProj) - sum(giveP, (p) => p.weekProj);
    const meRos = sum(getP, (p) => p.rosProj) - sum(giveP, (p) => p.rosProj);
    const warns: string[] = [];
    for (const p of getP) {
      if (OUT_STATUS.has(p.injury)) warns.push(`${p.name} is ${p.injury}`);
      if (p.pctStarted < 40 && !["DST", "K"].includes(p.pos)) warns.push(`${p.name} is a bench/flex piece (${fmt(p.pctStarted, 0)}% started)`);
    }
    // positional fit: does the added position address a need?
    const myByPos = me?.byPos ?? {};
    const needPos = ["RB", "WR", "TE"].filter((k) => (myByPos[k]?.[2]?.rosProj ?? 0) < 90);
    const helpsNeed = getP.some((p) => needPos.includes(p.pos));
    const verdict =
      meRos > 15 && meWeek > 1
        ? "Clear win — you get better now and for the season."
        : meRos > 15
          ? "Long-term win; roughly flat this week."
          : meRos < -15
            ? "You lose season value — pass unless you're desperate for a Week win."
            : helpsNeed && Math.abs(meRos) < 15
              ? "Even on value but fills a roster hole — worth proposing."
              : "Marginal — roughly even.";
    return { meWeek: Math.round(meWeek * 10) / 10, meRos: Math.round(meRos), warns, verdict, needPos };
  }, [giveP, getP, me]);

  // buy-low / sell-high: ROS value vs current % started (perceived value)
  const buyLow = useMemo(
    () =>
      players
        .filter((p) => !p.available && p.rosProj > 120 && p.pctStarted < 55 && !OUT_STATUS.has(p.injury))
        .sort((a, b) => b.rosProj - a.rosProj)
        .slice(0, 6),
    [players],
  );

  const toggle = (s: Set<string>, setter: (x: Set<string>) => void, id: string) => {
    const n = new Set(s);
    if (n.has(id)) n.delete(id);
    else n.add(id);
    setter(n);
  };

  if (!me) return <p className="card p-3 text-sm text-[var(--muted)]">Run the NFL sync first.</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <h1 className="text-xl font-semibold">Trade lab</h1>
        <select
          className="input ml-auto text-sm"
          value={their?.teamId ?? ""}
          onChange={(e) => {
            setRival(Number(e.target.value));
            setGet(new Set());
          }}
        >
          {rivals.map((t) => (
            <option key={t.teamId} value={t.teamId}>
              {t.name}
            </option>
          ))}
        </select>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <div className="card p-2">
          <div className="mb-1 text-xs font-semibold text-[var(--muted)]">YOU GIVE</div>
          <div className="flex flex-wrap">
            {[...me.players]
              .sort((a, b) => a.rosProj - b.rosProj)
              .map((p) => (
                <Chip key={p.extId} p={p} on={give.has(p.extId)} toggle={() => toggle(give, setGive, p.extId)} />
              ))}
          </div>
        </div>
        <div className="card p-2">
          <div className="mb-1 text-xs font-semibold text-[var(--muted)]">YOU GET</div>
          <div className="flex flex-wrap">
            {(their?.players ?? [])
              .slice()
              .sort((a, b) => b.rosProj - a.rosProj)
              .map((p) => (
                <Chip key={p.extId} p={p} on={get.has(p.extId)} toggle={() => toggle(get, setGet, p.extId)} />
              ))}
          </div>
        </div>
      </div>

      {evalTrade && (
        <div className="card space-y-2 p-3 text-sm">
          <div className="flex flex-wrap gap-x-6">
            <span>
              This week: <b style={{ color: evalTrade.meWeek >= 0 ? "var(--good)" : "var(--bad)" }}>
                {evalTrade.meWeek >= 0 ? "+" : ""}
                {fmt(evalTrade.meWeek)}
              </b>
            </span>
            <span>
              Rest of season: <b style={{ color: evalTrade.meRos >= 0 ? "var(--good)" : "var(--bad)" }}>
                {evalTrade.meRos >= 0 ? "+" : ""}
                {fmt(evalTrade.meRos, 0)}
              </b>{" "}
              (they get {evalTrade.meRos >= 0 ? "-" : "+"}
              {fmt(Math.abs(evalTrade.meRos), 0)})
            </span>
          </div>
          <p className="font-medium">{evalTrade.verdict}</p>
          {evalTrade.needPos.length > 0 && (
            <p className="text-xs text-[var(--muted)]">Your thin spots: {evalTrade.needPos.join(", ")}</p>
          )}
          {evalTrade.warns.length > 0 && (
            <ul className="list-disc pl-5 text-xs text-[var(--warn)]">
              {evalTrade.warns.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {buyLow.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold text-[var(--muted)]">BUY-LOW TARGETS (owned, high ROS value, low usage)</h2>
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Player</th>
                  <th>Owner</th>
                  <th className="num">ROS</th>
                  <th className="num hide-sm">% started</th>
                </tr>
              </thead>
              <tbody>
                {buyLow.map((p) => (
                  <tr key={p.extId}>
                    <td className="font-medium">
                      <span
                        className="mr-1 rounded px-0.5 text-[9px] font-bold text-white"
                        style={{ background: POS_COLOR[p.pos] }}
                      >
                        {p.pos}
                      </span>
                      {p.name} <span className="text-[var(--muted)]">{p.team}</span>
                    </td>
                    <td className="text-xs">{p.ownerName}</td>
                    <td className="num font-semibold">{fmt(p.rosProj, 0)}</td>
                    <td className="num hide-sm">{fmt(p.pctStarted, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <Legend
        items={[
          ["This week / ROS", "change in your projected points if the trade goes through"],
          ["✚", "currently OUT / IR / suspended"],
          ["Buy-low", "a rival's player whose rest-of-season projection outstrips how often they're being started — value you may be able to pry loose"],
          ["Thin spots", "positions where your 3rd-best player projects under a startable line"],
        ]}
      />
    </div>
  );
}
