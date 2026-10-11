import { useState } from "react";
import { $api, type Api } from "@/api/client";
import { fmt, signed } from "@/shared/format";
import { EmptyState, Legend, PosBadge, QueryView, SubHeading } from "@/shared/ui";
import { OppTag, type Player } from "./common";

const OUT = new Set(["OUT", "IR", "SUSPENSION", "DOUBTFUL"]);

export default function NflTradePage() {
  const [rival, setRival] = useState<number | null>(null);
  const q = $api.useQuery("get", "/api/nfl/trade", { params: { query: rival == null ? {} : { rival } } }, {
    placeholderData: (prev) => prev,
  });
  return <QueryView query={q}>{(lab) => <Lab lab={lab} setRival={setRival} />}</QueryView>;
}

function Chip({ p, on, toggle }: { p: Player; on: boolean; toggle: () => void }) {
  return (
    <button type="button" onClick={toggle} aria-pressed={on} title={`wk ${fmt(p.weekProj)} · ROS ${fmt(p.rosProj, 0)}`}
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

function Lab({ lab, setRival }: { lab: Api["NflTradeLab"]; setRival: (id: number) => void }) {
  const [give, setGive] = useState<string[]>([]);
  const [get, setGet] = useState<string[]>([]);
  const ev = $api.useQuery("post", "/api/nfl/trade/evaluate", { body: { give, get } }, {
    enabled: give.length + get.length > 0,
    placeholderData: (prev) => prev,
  });
  const { me, rival: their } = lab;
  if (!me) return <EmptyState title="No roster yet" hint="Waiting for the first NFL sync." />;
  const e = give.length + get.length > 0 ? ev.data : undefined;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <h1 className="text-xl font-semibold">Trade lab</h1>
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
          <SubHeading>Trades worth proposing — both lineups improve</SubHeading>
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>You give</th>
                  <th>You get</th>
                  <th>From</th>
                  <th className="num hide-sm">get xFP/g</th>
                  <th className="num">You +</th>
                  <th className="num hide-sm">Them +</th>
                </tr>
              </thead>
              <tbody>
                {lab.ideas.map((t) => (
                  <tr key={`${t.give.extId}-${t.get.extId}`}>
                    <td>
                      <PosBadge position={t.give.pos} small /> {t.give.name}
                    </td>
                    <td className="font-medium">
                      <PosBadge position={t.get.pos} small /> {t.get.name} <span className="text-[var(--muted)]">{t.get.team}</span>
                      <OppTag p={t.get} />
                    </td>
                    <td className="text-xs">{t.rivalName}</td>
                    <td className="num hide-sm">{t.get.expGames ? fmt(t.get.xfpG, 1) : "–"}</td>
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
            1-for-1 swaps that raise your best-lineup ROS total. <b>Them +</b> is the same for the rival — a positive
            number means they gain too, so it's an easy sell; a small negative is still worth floating.
          </p>
        </section>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        <div className="card p-2">
          <div className="mb-1 text-xs font-semibold text-[var(--muted)]">YOU GIVE</div>
          <div className="flex flex-wrap">
            {[...me.players].sort((a, b) => a.rosProj - b.rosProj).map((p) => (
              <Chip key={p.extId} p={p} on={give.includes(p.extId)} toggle={() => setGive((s) => toggled(s, p.extId))} />
            ))}
          </div>
        </div>
        <div className="card p-2">
          <div className="mb-1 text-xs font-semibold text-[var(--muted)]">YOU GET</div>
          <div className="flex flex-wrap">
            {[...(their?.players ?? [])].sort((a, b) => b.rosProj - a.rosProj).map((p) => (
              <Chip key={p.extId} p={p} on={get.includes(p.extId)} toggle={() => setGet((s) => toggled(s, p.extId))} />
            ))}
          </div>
        </div>
      </div>

      {e && (
        <div className="card space-y-2 p-3 text-sm">
          <div className="flex flex-wrap gap-x-6">
            <span>
              This week: <b style={{ color: tone(e.meWeek) }}>{signed(e.meWeek)}</b>
            </span>
            <span>
              Rest of season: <b style={{ color: tone(e.meRos) }}>{signed(e.meRos, 0)}</b>{" "}
              <span className="text-[var(--muted)]">(rival, raw projection: {signed(e.themRos, 0)})</span>
            </span>
          </div>
          <p className="font-medium">{e.verdict}</p>
          {e.needPos.length > 0 && <p className="text-xs text-[var(--muted)]">Your thin spots: {e.needPos.join(", ")}</p>}
          {e.warnings.length > 0 && (
            <ul className="list-disc pl-5 text-xs text-[var(--warn)]">
              {e.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {their && lab.theirSurplus.length > 0 && (
        <section className="space-y-2">
          <SubHeading>{their.name} — movable value (their non-starters, by positional value)</SubHeading>
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Player</th>
                  <th className="num">VOR</th>
                  <th className="num hide-sm">ROS</th>
                  <th className="num hide-sm">xFP/g</th>
                  <th className="num hide-sm">+/− exp</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {lab.theirSurplus.map(({ player: p, fillsNeed, tag }) => (
                  <tr key={p.extId}>
                    <td className="font-medium">
                      <PosBadge position={p.pos} small /> {p.name} <span className="text-[var(--muted)]">{p.team}</span>
                    </td>
                    <td className="num font-semibold">{fmt(p.vor, 0)}</td>
                    <td className="num hide-sm">{fmt(p.rosProj, 0)}</td>
                    <td className="num hide-sm">{p.expGames ? fmt(p.xfpG, 1) : "–"}</td>
                    <td className="num hide-sm"
                      style={{ color: !p.expGames ? undefined : p.fpOe <= -2 ? "var(--good)" : p.fpOe >= 2 ? "var(--warn)" : "var(--muted)" }}>
                      {p.expGames ? signed(p.fpOe, 1) : "–"}
                    </td>
                    <td className="text-xs">
                      {fillsNeed && <span className="text-[var(--good)]">fills your need</span>}
                      {tag && (
                        <span className="ml-1 font-semibold" style={{ color: tag === "buy-low" ? "var(--good)" : "var(--warn)" }}>
                          {tag}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <Legend
        items={[
          ["This week / ROS", "change in your projected points if the trade goes through — ROS is opportunity-adjusted (docks players riding TD/finishing luck, credits the unlucky)"],
          ["xFP/g · +/− exp", "expected fantasy points per game from the ffopportunity model, and how far actual output is over (+, regression risk) or under (−, buy-low) it"],
          ["buy-low / sell-high", "scoring well under / over what their opportunity expects — the swap value already accounts for this"],
          ["✚", "currently OUT / IR / suspended"],
          ["VOR", "value over replacement — rest-of-season points above a replacement-level starter AT THAT POSITION (so a QB and an RB are comparable — ranking by raw projection just shows QBs)"],
          ["Movable value", "the selected rival's players who don't make their own optimal lineup — what they can most afford to trade you"],
          ["Thin spots", "positions where your 3rd-best player projects under a startable line"],
        ]}
      />
    </div>
  );
}
