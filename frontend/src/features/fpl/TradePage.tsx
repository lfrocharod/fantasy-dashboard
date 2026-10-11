import { useState } from "react";
import { $api, type Api } from "@/api/client";
import { fmt, signed } from "@/shared/format";
import { EmptyState, Legend, PosBadge, QueryView, SubHeading, Toggle } from "@/shared/ui";
import { HORIZON_LABEL, HORIZONS, type Horizon, type Player } from "./common";

export default function FplTradePage() {
  const [horizon, setHorizon] = useState<Horizon>("medium");
  const q = $api.useQuery("get", "/api/fpl/trade", { params: { query: { horizon } } }, {
    placeholderData: (prev) => prev,
  });
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">Trade lab</h1>
        <div className="ml-auto">
          <Toggle value={horizon} options={HORIZONS} label={(h) => HORIZON_LABEL[h]} onChange={setHorizon} />
        </div>
      </div>
      <QueryView query={q}>{(lab) => <Lab lab={lab} horizon={horizon} />}</QueryView>
    </div>
  );
}

function Chip({ p, on, toggle }: { p: Player; on: boolean; toggle: () => void }) {
  return (
    <button type="button" onClick={toggle} aria-pressed={on} title={`6GW ${fmt(p.horizon, 0)} · ROS ${fmt(p.ros, 0)}`}
      className={`m-0.5 rounded border px-1.5 py-0.5 text-xs ${on ? "border-[var(--accent)] bg-[var(--accent)] text-white" : "border-[var(--border)]"}`}>
      <span className="mr-1">
        <PosBadge position={p.pos} small />
      </span>
      {p.name}
      {p.suspRisk && <span className="ml-0.5 text-[var(--warn)]">⚑</span>}
      {p.unavailable && <span className="ml-0.5 text-[var(--bad)]">✚</span>}
    </button>
  );
}

const toggled = (s: string[], id: string) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]);

function Lab({ lab, horizon }: { lab: Api["FplTradeLab"]; horizon: Horizon }) {
  const [rival, setRival] = useState("");
  const [give, setGive] = useState<string[]>([]);
  const [get, setGet] = useState<string[]>([]);
  const me = lab.me;
  const them = lab.rivals.find((m) => m.entryId === rival) ?? lab.rivals[0];
  const ev = $api.useQuery("post", "/api/fpl/trade/evaluate", { body: { give, get } }, {
    enabled: give.length + get.length > 0,
    placeholderData: (prev) => prev,
  });

  if (!me) return <EmptyState title="No roster data yet" hint="The next FPL sync pulls every manager's squad." />;
  const pick = (ids: string[], pool: Player[]) => pool.filter((p) => ids.includes(p.extId));
  const giveP = pick(give, me.players);
  const getP = pick(get, them?.players ?? []);
  const e = give.length + get.length > 0 ? ev.data : undefined;

  return (
    <>
      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <SubHeading>Build a trade with</SubHeading>
          <select className="input text-sm" value={them?.entryId ?? ""} aria-label="rival"
            onChange={(x) => {
              setRival(x.target.value);
              setGet([]);
            }}>
            {lab.rivals.map((m) => (
              <option key={m.entryId} value={m.entryId}>{m.name}</option>
            ))}
          </select>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <div className="card p-2">
            <div className="mb-1 text-xs font-semibold text-[var(--muted)]">YOU GIVE</div>
            <div className="flex flex-wrap">
              {[...me.players].sort((a, b) => a.horizon - b.horizon).map((p) => (
                <Chip key={p.extId} p={p} on={give.includes(p.extId)} toggle={() => setGive((s) => toggled(s, p.extId))} />
              ))}
            </div>
          </div>
          <div className="card p-2">
            <div className="mb-1 text-xs font-semibold text-[var(--muted)]">YOU GET</div>
            <div className="flex flex-wrap">
              {[...(them?.players ?? [])].sort((a, b) => b.horizon - a.horizon).map((p) => (
                <Chip key={p.extId} p={p} on={get.includes(p.extId)} toggle={() => setGet((s) => toggled(s, p.extId))} />
              ))}
            </div>
          </div>
        </div>
        {e && (
          <div className="card space-y-2 p-3 text-sm">
            <div className="flex flex-wrap items-center gap-x-6 gap-y-1">
              <span>
                Give <b>{giveP.map((p) => p.pos).sort().join("+") || "—"}</b> · Get{" "}
                <b>{getP.map((p) => p.pos).sort().join("+") || "—"}</b>
              </span>
              {!e.balanced && <span className="font-semibold text-[var(--bad)]">not position-balanced</span>}
            </div>
            <div className="table-wrap">
              <table className="dtable text-xs">
                <thead>
                  <tr>
                    <th>Window</th>
                    <th className="num">You Δ</th>
                    <th className="num">{them?.name} Δ</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Next GW</td>
                    <DeltaCell v={e.meShort} />
                    <DeltaCell v={e.themShort} />
                  </tr>
                  <tr>
                    <td>Next 6 GW</td>
                    <DeltaCell v={e.meMedium} />
                    <DeltaCell v={e.themMedium} />
                  </tr>
                  <tr>
                    <td>Rest of season</td>
                    <DeltaCell v={e.meSeason} />
                    <DeltaCell v={e.themSeason} />
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="font-medium">{e.verdict}</p>
            {e.warnings.length > 0 && (
              <ul className="list-disc pl-5 text-xs text-[var(--warn)]">
                {e.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>

      <section className="space-y-2">
        <SubHeading>Suggested trades ({HORIZON_LABEL[horizon]})</SubHeading>
        {lab.suggestions.length === 0 ? (
          <p className="text-sm text-[var(--muted)]">
            No position-balanced swap clearly upgrades the XI you'd field over {HORIZON_LABEL[horizon]} without fleecing
            the rival by neutral value.
          </p>
        ) : (
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Rival</th>
                  <th>You give</th>
                  <th>You get</th>
                  <th className="num" title="gain to the XI you'd actually field over the window">XI +</th>
                  <th className="num hide-sm" title="swing for the rival by neutral value (season ppg + rank) — ≥0 means they'd want it too">Them</th>
                </tr>
              </thead>
              <tbody>
                {lab.suggestions.map((t) => (
                  <tr key={`${t.rivalName}-${t.give.map((p) => p.extId).join("+")}-${t.get.map((p) => p.extId).join("+")}`}>
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
                          {p.oppTag && (
                            <span className="ml-1 text-[10px] font-semibold" style={{ color: p.oppTag === "value" ? "var(--good)" : "var(--warn)" }}
                              title={`season xGI/90 ${p.xgi90.toFixed(2)}${p.pos === "DEF" || p.pos === "GKP" ? ` · xGC/90 ${p.xgc90.toFixed(2)}` : ""}`}>
                              {p.oppTag}
                            </span>
                          )}
                        </div>
                      ))}
                    </td>
                    <td className="num font-semibold text-[var(--good)]">+{fmt(t.myGain, 0)}</td>
                    <td className="num hide-sm" style={{ color: t.theirGain >= 0 ? "var(--good)" : "var(--muted)" }}>
                      {signed(t.theirGain, 0)}
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
          ["You Δ / XI +", "the change to the value of the XI you can actually field — a player who wouldn't start you barely moves it (that's the point). Projections are nudged ±~10% by season xGI/90 (MID/FWD) and xGC/90 (DEF/GKP)."],
          ["Them Δ / Them", "the swing for the rival valued the way a typical manager would (season points-per-game + draft rank), not by your form-sensitive projection. ≥ 0 means it's a fair ask; a big negative means they'll say no."],
          ["value / output-led", "the underlying stats run ahead of / behind current output — a buy signal / a regression flag"],
          ["⚑", "a booking from a suspension — matters for medium/long moves, not a one-week rental"],
          ["✚", "currently injured / suspended / doubtful"],
          ["balanced", "a draft trade must have the same positions on both sides"],
        ]}
      />
    </>
  );
}

function DeltaCell({ v }: { v: number }) {
  return (
    <td className="num font-semibold" style={{ color: v > 0.3 ? "var(--good)" : v < -0.3 ? "var(--bad)" : "var(--muted)" }}>
      {signed(v, 1)}
    </td>
  );
}
