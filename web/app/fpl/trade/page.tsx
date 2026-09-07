"use client";

import { useEffect, useMemo, useState } from "react";
import { Legend } from "@/components/ui";
import { fmt } from "@/lib/format";
import type { DraftConfig } from "@/lib/draft/queries";
import {
  HORIZON_LABEL,
  evaluateTrade,
  groupByManager,
  loadBoard,
  tradeIdeas,
  type FplPlayer,
  type Horizon,
} from "../lib";

const POS_COLOR: Record<string, string> = {
  GKP: "#6b7280", DEF: "#1f6feb", MID: "#1a7f37", FWD: "#cf222e",
};

function Chip({ p, on, toggle }: { p: FplPlayer; on: boolean; toggle: () => void }) {
  return (
    <button
      onClick={toggle}
      className={`m-0.5 rounded border px-1.5 py-0.5 text-xs ${
        on ? "border-[var(--accent)] bg-[var(--accent)] text-white" : "border-[var(--border)]"
      }`}
      title={`6GW ${fmt(p.horizon, 0)} · ROS ${fmt(p.ros, 0)}`}
    >
      <span
        className="mr-1 rounded px-0.5 text-[9px] font-bold text-white"
        style={{ background: POS_COLOR[p.pos] }}
      >
        {p.pos}
      </span>
      {p.name}
      {p.suspRisk && <span className="ml-0.5 text-[var(--warn)]">⚑</span>}
      {p.unavailable && <span className="ml-0.5 text-[var(--bad)]">✚</span>}
    </button>
  );
}

export default function TradePage() {
  const [players, setPlayers] = useState<FplPlayer[]>([]);
  const [picks, setPicks] = useState<
    { playerExtId: string; teamId: number; teamName: string; isMine: boolean }[]
  >([]);
  const [config, setConfig] = useState<DraftConfig | null>(null);
  const [rival, setRival] = useState<string>("");
  const [give, setGive] = useState<Set<string>>(new Set());
  const [get, setGet] = useState<Set<string>>(new Set());
  const [horizon, setHorizon] = useState<Horizon>("medium");

  useEffect(() => {
    loadBoard().then((d) => {
      setPlayers(d.players);
      setPicks(d.picks);
      setConfig(d.config);
    });
  }, []);

  const fallbackNames = useMemo(
    () =>
      Object.fromEntries(
        ((config?.standings ?? []) as { name: string; entry_id: number | null }[]).map((s) => [
          String(s.entry_id),
          s.name,
        ]),
      ),
    [config],
  );
  const managers = useMemo(
    () => groupByManager(players, picks, config?.entryId ?? null, fallbackNames),
    [players, picks, config, fallbackNames],
  );
  const me = managers.find((m) => m.isMine);
  const rivals = managers.filter((m) => !m.isMine);
  const theirTeam = rivals.find((m) => m.entryId === rival) ?? rivals[0];

  const byId = useMemo(() => new Map(players.map((p) => [p.extId, p])), [players]);
  const giveP = [...give].map((id) => byId.get(id)!).filter(Boolean);
  const getP = [...get].map((id) => byId.get(id)!).filter(Boolean);
  const evaluation = giveP.length || getP.length ? evaluateTrade(giveP, getP) : null;

  const owners = useMemo(() => {
    const m = new Map<string, { name: string; ids: Set<string> }>();
    for (const mg of rivals) m.set(mg.entryId, { name: mg.name, ids: new Set(mg.players.map((p) => p.extId)) });
    return m;
  }, [rivals]);

  const suggestions = useMemo(
    () => (me ? tradeIdeas(me.players, players, owners, 4, horizon) : []),
    [me, players, owners, horizon],
  );

  const toggle = (set: Set<string>, setter: (s: Set<string>) => void, id: string) => {
    const n = new Set(set);
    if (n.has(id)) n.delete(id);
    else n.add(id);
    setter(n);
  };

  if (!me) {
    return (
      <p className="card p-3 text-sm text-[var(--muted)]">
        No roster data — run <code>./draft.sh --sport fpl --sync</code>.
      </p>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">Trade lab</h1>
        <div className="ml-auto flex gap-1 text-xs">
          {(["short", "medium", "season"] as const).map((h) => (
            <button
              key={h}
              onClick={() => setHorizon(h)}
              className={`rounded px-2 py-1 ${horizon === h ? "bg-[var(--accent)] text-white" : "border border-[var(--border)]"}`}
            >
              {HORIZON_LABEL[h]}
            </button>
          ))}
        </div>
      </div>

      {/* ---- PROPOSER ---- */}
      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-[var(--muted)]">BUILD A TRADE with</span>
          <select
            className="input text-sm"
            value={theirTeam?.entryId ?? ""}
            onChange={(e) => {
              setRival(e.target.value);
              setGet(new Set());
            }}
          >
            {rivals.map((m) => (
              <option key={m.entryId} value={m.entryId}>
                {m.name}
              </option>
            ))}
          </select>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <div className="card p-2">
            <div className="mb-1 text-xs font-semibold text-[var(--muted)]">YOU GIVE</div>
            <div className="flex flex-wrap">
              {[...me.players]
                .sort((a, b) => a.horizon - b.horizon)
                .map((p) => (
                  <Chip key={p.extId} p={p} on={give.has(p.extId)} toggle={() => toggle(give, setGive, p.extId)} />
                ))}
            </div>
          </div>
          <div className="card p-2">
            <div className="mb-1 text-xs font-semibold text-[var(--muted)]">YOU GET</div>
            <div className="flex flex-wrap">
              {(theirTeam?.players ?? [])
                .slice()
                .sort((a, b) => b.horizon - a.horizon)
                .map((p) => (
                  <Chip key={p.extId} p={p} on={get.has(p.extId)} toggle={() => toggle(get, setGet, p.extId)} />
                ))}
            </div>
          </div>
        </div>

        {evaluation && (
          <div className="card space-y-2 p-3 text-sm">
            <div className="flex flex-wrap items-center gap-x-6 gap-y-1">
              <span>
                Give <b>{giveP.map((p) => p.pos).sort().join("+") || "—"}</b> · Get{" "}
                <b>{getP.map((p) => p.pos).sort().join("+") || "—"}</b>
              </span>
              {!evaluation.balanced && (
                <span className="font-semibold text-[var(--bad)]">not position-balanced</span>
              )}
            </div>
            <div className="table-wrap">
              <table className="dtable text-xs">
                <thead>
                  <tr>
                    <th>Window</th>
                    <th className="num">You Δ</th>
                    <th className="num">{theirTeam?.name} Δ</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Next GW</td>
                    <DeltaCell v={evaluation.meShort} />
                    <DeltaCell v={evaluation.themShort} />
                  </tr>
                  <tr>
                    <td>Next 6 GW</td>
                    <DeltaCell v={evaluation.meMedium} />
                    <DeltaCell v={evaluation.themMedium} />
                  </tr>
                  <tr>
                    <td>Rest of season</td>
                    <DeltaCell v={evaluation.meSeason} />
                    <DeltaCell v={evaluation.themSeason} />
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="font-medium">{evaluation.verdict}</p>
            {evaluation.warnings.length > 0 && (
              <ul className="list-disc pl-5 text-xs text-[var(--warn)]">
                {evaluation.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>

      {/* ---- AUTO SUGGESTIONS ---- */}
      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-[var(--muted)]">
          SUGGESTED TRADES ({HORIZON_LABEL[horizon]})
        </h2>
        {suggestions.length === 0 ? (
          <p className="text-sm text-[var(--muted)]">
            No position-balanced swap clearly improves your {HORIZON_LABEL[horizon]} projection
            without hurting the rival.
          </p>
        ) : (
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Rival</th>
                  <th>You give</th>
                  <th>You get</th>
                  <th className="num">You +</th>
                  <th className="num hide-sm">Them +</th>
                </tr>
              </thead>
              <tbody>
                {suggestions.map((t, i) => (
                  <tr key={i}>
                    <td>{t.rivalName}</td>
                    <td>
                      {t.give.map((p) => (
                        <div key={p.extId} className="whitespace-nowrap">
                          <span className="text-[10px] text-[var(--muted)]">{p.pos}</span> {p.name}
                        </div>
                      ))}
                    </td>
                    <td className="font-medium">
                      {t.get.map((p) => (
                        <div key={p.extId} className="whitespace-nowrap">
                          <span className="text-[10px] text-[var(--muted)]">{p.pos}</span> {p.name}
                        </div>
                      ))}
                    </td>
                    <td className="num font-semibold text-[var(--good)]">+{fmt(t.myGain, 0)}</td>
                    <td
                      className="num hide-sm"
                      style={{ color: t.theirGain >= 0 ? "var(--good)" : "var(--muted)" }}
                    >
                      {t.theirGain >= 0 ? "+" : ""}
                      {fmt(t.theirGain, 0)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <Legend
        items={[
          ["Windows", "next GW (short), next 6 GW (medium), rest of season (long)"],
          ["Δ", "change in projected draft points for that side"],
          ["⚑", "a booking from a suspension — matters for medium/long moves, not a one-week rental"],
          ["✚", "currently injured / suspended / doubtful"],
          ["balanced", "a draft trade must have the same positions on both sides"],
        ]}
      />
    </div>
  );
}

function DeltaCell({ v }: { v: number }) {
  return (
    <td
      className="num font-semibold"
      style={{ color: v > 0.3 ? "var(--good)" : v < -0.3 ? "var(--bad)" : "var(--muted)" }}
    >
      {v > 0 ? "+" : ""}
      {fmt(v, 1)}
    </td>
  );
}
