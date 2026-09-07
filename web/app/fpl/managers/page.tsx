"use client";

import { useEffect, useMemo, useState } from "react";
import { Legend } from "@/components/ui";
import { fmt } from "@/lib/format";
import type { DraftConfig } from "@/lib/draft/queries";
import { groupByManager, loadBoard, type FplPlayer, type Manager } from "../lib";

const POS_ORDER = ["GKP", "DEF", "MID", "FWD"];
const POS_COLOR: Record<string, string> = {
  GKP: "#6b7280", DEF: "#1f6feb", MID: "#1a7f37", FWD: "#cf222e",
};

export default function ManagersPage() {
  const [players, setPlayers] = useState<FplPlayer[]>([]);
  const [picks, setPicks] = useState<
    { playerExtId: string; teamId: number; teamName: string; isMine: boolean }[]
  >([]);
  const [config, setConfig] = useState<DraftConfig | null>(null);
  const [metric, setMetric] = useState<"medium" | "season">("season");

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

  if (!managers.length) {
    return (
      <p className="card p-3 text-sm text-[var(--muted)]">
        No roster data yet — run <code>./draft.sh --sport fpl --sync</code>.
      </p>
    );
  }

  const v = (p: FplPlayer) => (metric === "medium" ? p.horizon : p.ros);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">Manager rosters</h1>
        <div className="ml-auto flex gap-1 text-xs">
          {(["medium", "season"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMetric(m)}
              className={`rounded px-2 py-1 ${metric === m ? "bg-[var(--accent)] text-white" : "border border-[var(--border)]"}`}
            >
              {m === "medium" ? "next 6 GW" : "rest of season"}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {managers.map((mg) => (
          <ManagerCard key={mg.entryId} mg={mg} metric={metric} v={v} />
        ))}
      </div>

      <Legend
        items={[
          ["value", `projected draft points — ${metric === "medium" ? "next 6 gameweeks" : "rest of season"}`],
          ["yellow ⚑", "one booking from a suspension"],
          ["injured / doubt", "not expected to feature next GW"],
          ["Σ", "roster total for the selected window"],
        ]}
      />
    </div>
  );
}

function ManagerCard({
  mg,
  metric,
  v,
}: {
  mg: Manager;
  metric: "medium" | "season";
  v: (p: FplPlayer) => number;
}) {
  const total = metric === "medium" ? mg.total.medium : mg.total.season;
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
            {POS_ORDER.map((pos) => {
              const list = mg.byPos[pos] ?? [];
              return list.map((p, i) => (
                <tr key={p.extId}>
                  {i === 0 && (
                    <td
                      rowSpan={list.length}
                      className="align-top font-bold text-white"
                    >
                      <span
                        className="rounded px-1"
                        style={{ background: POS_COLOR[pos] }}
                      >
                        {pos}
                      </span>
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
                  <td className="text-[var(--muted)]">{p.team}</td>
                  <td className="num font-semibold">{fmt(v(p), metric === "medium" ? 0 : 0)}</td>
                </tr>
              ));
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
