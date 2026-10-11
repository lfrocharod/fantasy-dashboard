import { useState } from "react";
import { $api, type Api } from "@/api/client";
import { dateTime, fmt, signed } from "@/shared/format";
import { EmptyState, Legend, PosBadge, QueryView, SubHeading } from "@/shared/ui";
import type { Player } from "./common";

const OUT = new Set(["OUT", "SUSPENSION", "INJURY_RESERVE"]);

export default function NbaTradePage() {
  const [rival, setRival] = useState<number | null>(null);
  const q = $api.useQuery("get", "/api/nba/trade", { params: { query: rival == null ? {} : { rival } } }, {
    placeholderData: (prev) => prev,
  });
  return <QueryView query={q}>{(lab) => <Lab lab={lab} setRival={setRival} />}</QueryView>;
}

function Chip({ p, on, toggle }: { p: Player; on: boolean; toggle: () => void }) {
  return (
    <button type="button" onClick={toggle} aria-pressed={on}
      title={`${fmt(p.fppg)}/g · ${p.gamesLeft} games this matchup · ROS ${fmt(p.ros, 0)} · ${p.playoffGames} playoff games`}
      className={`m-0.5 rounded border px-1.5 py-0.5 text-xs ${on ? "border-[var(--accent)] bg-[var(--accent)] text-white" : "border-[var(--border)]"}`}>
      <span className="mr-1">
        <PosBadge position={p.pos} small />
      </span>
      {p.name}
      {OUT.has(p.injury) && <span className="ml-0.5 text-[var(--bad)]">✚</span>}
    </button>
  );
}

const toggled = (s: string[], id: string) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]);
const tone = (v: number) => (v >= 0 ? "var(--good)" : "var(--bad)");

function Lab({ lab, setRival }: { lab: Api["NbaTradeLab"]; setRival: (id: number) => void }) {
  const [give, setGive] = useState<string[]>([]);
  const [get, setGet] = useState<string[]>([]);
  const ev = $api.useQuery("post", "/api/nba/trade/evaluate", { body: { give, get } }, {
    enabled: give.length + get.length > 0,
    placeholderData: (prev) => prev,
  });
  const { me, rival: their } = lab;
  if (!me || me.players.length === 0) return <EmptyState title="No roster yet" hint="Waiting for the first NBA sync." />;
  const e = give.length + get.length > 0 ? ev.data : undefined;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-semibold">Trade lab</h1>
        <span className="text-sm text-[var(--muted)]">
          {fmt(lab.weeksLeft)} weeks left{lab.tradeDeadline && ` · deadline ${dateTime(lab.tradeDeadline)}`}
        </span>
        <select className="input ml-auto text-sm" value={their?.teamId ?? ""} aria-label="rival"
          onChange={(x) => {
            setRival(Number(x.target.value));
            setGet([]);
          }}>
          {lab.rivals.map((t) => (
            <option key={t.teamId} value={t.teamId}>{t.name}</option>
          ))}
        </select>
      </div>

      {lab.ideas.length > 0 && (
        <section className="space-y-2">
          <SubHeading>Trades worth proposing</SubHeading>
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>You give</th>
                  <th>You get</th>
                  <th>From</th>
                  <th className="num">You +</th>
                  <th className="num hide-sm">Them, on projections</th>
                </tr>
              </thead>
              <tbody>
                {lab.ideas.map((t) => (
                  <tr key={`${t.give.extId}-${t.get.extId}`}>
                    <td>
                      {t.give.name} <span className="text-xs text-[var(--muted)]">{fmt(t.give.fppg)}/g</span>
                    </td>
                    <td className="font-medium">
                      {t.get.name} <span className="text-xs text-[var(--muted)]">{t.get.team} · {fmt(t.get.fppg)}/g</span>
                    </td>
                    <td className="text-xs">{t.rivalName}</td>
                    <td className="num font-semibold text-[var(--good)]">+{fmt(t.myGain, 0)}</td>
                    <td className="num hide-sm" style={{ color: t.theirGain >= 0 ? "var(--good)" : "var(--muted)" }}>
                      {signed(t.theirGain, 0)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-[var(--muted)]">
            One-for-one swaps that add rest-of-season points for you (this season's form, and the games each team has
            left) while looking even or better for them on ESPN's preseason projections — the numbers most managers trade
            on. Your two best players are never offered.
          </p>
        </section>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        <div className="card p-2">
          <div className="mb-1 text-xs font-semibold text-[var(--muted)]">YOU GIVE</div>
          <div className="flex flex-wrap">
            {[...me.players].sort((a, b) => a.ros - b.ros).map((p) => (
              <Chip key={p.extId} p={p} on={give.includes(p.extId)} toggle={() => setGive((s) => toggled(s, p.extId))} />
            ))}
          </div>
        </div>
        <div className="card p-2">
          <div className="mb-1 text-xs font-semibold text-[var(--muted)]">YOU GET</div>
          <div className="flex flex-wrap">
            {[...(their?.players ?? [])].sort((a, b) => b.ros - a.ros).map((p) => (
              <Chip key={p.extId} p={p} on={get.includes(p.extId)} toggle={() => setGet((s) => toggled(s, p.extId))} />
            ))}
          </div>
        </div>
      </div>

      {e && (
        <div className="card space-y-2 p-4 text-sm">
          <div className="flex flex-wrap gap-6">
            <div>
              <div className="text-xs text-[var(--muted)]">Your rest of season</div>
              <div className="text-xl font-semibold" style={{ color: tone(e.myRos) }}>{signed(e.myRos, 0)}</div>
            </div>
            <div>
              <div className="text-xs text-[var(--muted)]">This matchup</div>
              <div className="text-xl font-semibold" style={{ color: tone(e.myWeek) }}>{signed(e.myWeek, 0)}</div>
            </div>
            <div>
              <div className="text-xs text-[var(--muted)]">Playoff games</div>
              <div className="text-xl font-semibold" style={{ color: tone(e.myPlayoffGames) }}>{signed(e.myPlayoffGames, 0)}</div>
            </div>
            <div>
              <div className="text-xs text-[var(--muted)]">Them, on projections</div>
              <div className="text-xl font-semibold" style={{ color: tone(e.theirRos) }}>{signed(e.theirRos, 0)}</div>
            </div>
          </div>
          <div className="font-medium">{e.verdict}</div>
          {e.rosterMoves.length > 0 && <div className="text-xs text-[var(--muted)]">Then: {e.rosterMoves.join("; ")}.</div>}
          {e.warnings.map((w) => (
            <div key={w} className="text-xs text-[var(--warn)]">⚠ {w}</div>
          ))}
        </div>
      )}

      <Legend
        items={[
          ["rest of season", "change in your total points to come: per-game rates × each player's remaining games × the share they're expected to play, plus the roster spot an uneven trade frees or costs"],
          ["this matchup", "change in this matchup's lineup-aware projection"],
          ["playoff games", "change in your players' NBA games during the fantasy playoffs"],
          ["them, on projections", "how the rival would see it on ESPN's projections — negative means a harder sell"],
        ]}
      />
    </div>
  );
}
