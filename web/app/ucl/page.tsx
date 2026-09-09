import { Checklist, EmptyState, Legend, PosBadge, StatCard, StatusDot, Section } from "@/components/ui";
import { fmt, money, timeUntil, dateTime } from "@/lib/format";
import {
  getCurrentMatchday,
  getFixtures,
  getLeagueTable,
  getLiveHistory,
  getLiveRivals,
  getLiveState,
  getMySquad,
  confirmedOf,
  leaguePhaseStrategy,
  type SquadRow,
} from "@/lib/ucl/queries";
import { hasUsableXg } from "@/lib/ucl/xg";
import { bestXiPlusCaptain } from "@/lib/ucl/score";
import { LiveMatchday } from "./LiveMatchday";
import { CaptaincyCard, type CaptainsBlob } from "./CaptaincyCard";
import { getSetting, getSettings, KEYS } from "@/lib/settings";
import { POSITIONS } from "@/lib/ucl/formation";
import { FDR_TEXT, posFdr, type Pos } from "@/lib/fdr";

interface Check {
  ok: boolean;
  text: string;
}

function buildChecklist(squad: SquadRow[], opt: Record<string, unknown>): Check[] {
  const checks: Check[] = [];
  const squadIds = new Set(squad.map((r) => r.playerId));
  const cap = squad.find((r) => r.isCaptain);
  const rawSafe = (opt.captains as { safePick?: { playerId?: number; name?: string } } | undefined)?.safePick;
  // only trust the model's pick if it's actually one of YOUR players — a stale
  // pre-season run can name a dream-team player you never owned.
  const safe = rawSafe && squadIds.has(rawSafe.playerId ?? -1) ? rawSafe : undefined;
  checks.push({
    ok: !!cap && (!safe || cap.playerId === safe.playerId),
    text: cap
      ? safe && cap.playerId !== safe.playerId
        ? `Captain is ${cap.name} — model prefers ${safe.name}`
        : `Captain set (${cap.name})`
      : "No captain set",
  });
  const starters = squad.filter((r) => r.isStarter);
  const flagged = starters.filter((r) => {
    const c = confirmedOf(r);
    if (c === "start") return false; // officially in the XI — no flag
    if (c === "bench") return true; // officially benched — definitely flag
    return (r.statusCode ?? 0) >= 1 || (r.startProb ?? 1) < 0.5;
  });
  checks.push({
    ok: flagged.length === 0,
    text: flagged.length
      ? `${flagged.length} starter(s) benched / injured / rotation risk: ${flagged.map((r) => r.name).join(", ")}`
      : "No injury or rotation flags in your XI",
  });
  const benched = starters.length < 11;
  checks.push({ ok: !benched, text: benched ? `Only ${starters.length} starters set` : "Full XI selected" });
  const timing = opt.matchdayTiming as { days?: number; liveOptions?: string[] } | undefined;
  const squadNames = new Set(squad.map((r) => r.name));
  const liveOpts = (timing?.liveOptions ?? []).filter((n) => squadNames.has(n));
  if (timing?.days && timing.days > 1 && liveOpts.length) {
    checks.push({
      ok: true,
      text: `Bench your day-${timing.days} players as live options: ${liveOpts.slice(0, 3).join(", ")}`,
    });
  }
  const transfers = opt.transfers as unknown[] | undefined;
  if (transfers?.length) {
    checks.push({ ok: false, text: `${transfers.length} transfer(s) suggested — see Optimizer` });
  }
  return checks;
}

export const dynamic = "force-dynamic";

export default async function UclOverview() {
  const md = await getCurrentMatchday();
  const live = await getLiveState();
  // the live blob may be for a just-finished matchday during the roll-over
  // window, so key history/fixtures off its own matchday
  const liveMd = live?.matchday ?? md;
  const [squad, fixtures, table, cfg, optRaw, liveHistory, liveRivals] =
    await Promise.all([
      getMySquad(md),
      getFixtures(liveMd),
      getLeagueTable(md),
      getSettings([KEYS.deadline]),
      getSetting(KEYS.optimizerOutput),
      getLiveHistory(liveMd),
      getLiveRivals(),
    ]);
  let opt: Record<string, unknown> = {};
  try {
    opt = optRaw ? JSON.parse(optRaw) : {};
  } catch {
    /* ignore */
  }

  if (squad.length === 0) {
    return (
      <EmptyState
        title={`No squad loaded for matchday ${md}`}
        hint="Connect your UEFA account in Settings, then run the ingestion job."
      />
    );
  }

  const oppByTeam: Record<
    string,
    { opp: string; home: boolean; oppAtk: number; oppDef: number; ownAtk: number; ownDef: number }
  > = {};
  for (const f of fixtures) {
    oppByTeam[f.homeTeam] = {
      opp: f.awayTeam,
      home: true,
      oppAtk: f.awayAtk ?? 1,
      oppDef: f.awayDef ?? 1,
      ownAtk: f.homeAtk ?? 1,
      ownDef: f.homeDef ?? 1,
    };
    oppByTeam[f.awayTeam] = {
      opp: f.homeTeam,
      home: false,
      oppAtk: f.homeAtk ?? 1,
      oppDef: f.homeDef ?? 1,
      ownAtk: f.awayAtk ?? 1,
      ownDef: f.awayDef ?? 1,
    };
  }

  const captainPick = [...squad].sort((a, b) => (b.xpts ?? 0) - (a.xpts ?? 0))[0];
  const { total: projTotal } = bestXiPlusCaptain(squad);
  const myRow = table.rows.find((r) => r.entryId === table.myEntryId);
  const liveNow = live; // ingest only writes the blob for an active / just-finished MD
  const strategy = leaguePhaseStrategy(table.rows, table.myEntryId, md);
  const squadIds = new Set(squad.map((r) => r.playerId));
  const setCaptainId = squad.find((r) => r.isCaptain)?.playerId ?? null;
  const STRAT_TONE = { protect: "good", hold: "warn", chase: "accent", free: "muted" } as const;

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
        <StatCard label="Matchday" value={md} />
        <StatCard
          label={liveNow ? "Live" : "Deadline"}
          value={liveNow ? (liveNow.state === "finished" ? "✓ FT" : "🔴") : timeUntil(cfg[KEYS.deadline] ?? null)}
          sub={liveNow ? `${liveNow.played}/${liveNow.starters} played` : undefined}
        />
        <StatCard
          label={liveNow ? "Proj. finish" : "Proj. total"}
          value={fmt(liveNow ? liveNow.projectedFinish : projTotal, 0)}
          sub={liveNow ? `${fmt(liveNow.securedPoints, 0)} secured` : "best XI + captain"}
        />
        <StatCard
          label="Captain pick"
          value={captainPick?.name.split(" ").slice(-1)[0] ?? "–"}
          sub={`${fmt(captainPick?.xpts)} xPts`}
        />
        <StatCard label="Squad value" value={money(squad.reduce((a, r) => a + r.price, 0))} />
        <StatCard
          label="League rank"
          value={myRow?.rank ?? "–"}
          sub={table.rows.length ? `of ${table.rows.length}` : undefined}
        />
      </div>

      {liveNow ? (
        <LiveMatchday
          live={liveNow}
          history={liveHistory}
          rivals={liveRivals && liveRivals.matchday === liveMd ? liveRivals : null}
        />
      ) : (
        <>
          {strategy && (
            <div
              className="card p-3 text-sm"
              style={{ borderLeft: `3px solid var(--${STRAT_TONE[strategy.mode]})` }}
            >
              <b style={{ color: `var(--${STRAT_TONE[strategy.mode]})` }}>
                {strategy.mode.toUpperCase()}
              </b>{" "}
              {strategy.text}
            </div>
          )}

          <CaptaincyCard
            captains={(opt.captains ?? {}) as CaptainsBlob}
            squadIds={squadIds}
            currentCaptainId={setCaptainId}
            strategy={strategy}
          />

          <Section title="Pre-deadline checklist">
            <Checklist items={buildChecklist(squad, opt)} />
          </Section>
        </>
      )}

      <Section title="Your squad">
        <div className="card table-wrap">
          <SquadTable rows={squad} captainId={captainPick?.playerId} oppByTeam={oppByTeam} />
        </div>
        <Legend
          items={[
            ["Opp colour", "position-aware fixture difficulty (green easy … red hard): forwards weigh the opponent's defence, keepers their attack, defenders mostly clean-sheet risk plus some set-piece upside, midfielders mostly attacking. (H) home, (A) away"],
            ["xPts", "expected points this matchday (our model)"],
            ["xMin", "expected minutes played"],
            ["P(start)", "chance of starting"],
            ["Form", "UEFA points per game this season"],
            ["xGI90", "expected goal involvements per 90 (non-penalty xG + xA) this domestic-league season (Sofascore, all leagues) — the underlying signal behind output."],
            ["🅲", "recommended captain (raw max — see Optimizer for the constrained pick)"],
          ]}
        />
      </Section>

      {/* redundant while the Live panel is up — it has its own fixture strip */}
      {!liveNow && (
      <Section title={`Matchday ${liveMd} fixtures`}>
        {fixtures.length === 0 ? (
          <EmptyState title="No fixtures loaded for this matchday" />
        ) : (
          <div className="card table-wrap">
            <table className="dtable">
              <thead>
                <tr>
                  <th>Kickoff</th>
                  <th>Home</th>
                  <th>Away</th>
                  <th className="num">Score</th>
                  <th className="num">xG (H)</th>
                  <th className="num">xG (A)</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {fixtures.map((f) => {
                  const played = f.status === "finished" || f.status === "live";
                  return (
                  <tr key={String(f.matchId)}>
                    <td>{f.kickoff ? dateTime(f.kickoff) : "TBD"}</td>
                    <td>{f.homeTeam}</td>
                    <td>{f.awayTeam}</td>
                    <td className="num font-semibold tabular-nums">
                      {played ? `${f.homeGoals ?? 0}–${f.awayGoals ?? 0}` : "–"}
                    </td>
                    <td className="num">{fmt(f.homeXg)}</td>
                    <td className="num">{fmt(f.awayXg)}</td>
                    <td>{f.status}</td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <Legend items={[["xG (H/A)", "expected goals for the home / away team (fixture difficulty)"]]} />
      </Section>
      )}
    </div>
  );
}

function SquadTable({
  rows,
  captainId,
  oppByTeam,
}: {
  rows: SquadRow[];
  captainId?: number;
  oppByTeam: Record<
    string,
    { opp: string; home: boolean; oppAtk: number; oppDef: number; ownAtk: number; ownDef: number }
  >;
}) {
  const ordered = POSITIONS.flatMap((pos) =>
    rows
      .filter((r) => r.position === pos)
      .sort((a, b) => (b.xpts ?? 0) - (a.xpts ?? 0)),
  );
  return (
    <table className="dtable">
      <thead>
        <tr>
          <th>Pos</th>
          <th>Player</th>
          <th>Team</th>
          <th>Opp</th>
          <th className="num">Price</th>
          <th className="num">Form</th>
          <th className="num" title="expected goal involvements per 90 (non-penalty xG + xA), last-5 window">xGI90</th>
          <th className="num">P(start)</th>
          <th className="num">xMin</th>
          <th className="num">xPts</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {ordered.map((r) => {
          const fx = oppByTeam[r.teamName];
          const fdr = fx
            ? posFdr(fx.oppAtk, fx.oppDef, fx.home, r.position as Pos, "ucl", fx.ownAtk, fx.ownDef)
            : null;
          return (
          <tr key={r.playerId}>
            <td>
              <PosBadge position={r.position} />
            </td>
            <td>
              {r.name} <StatusDot code={r.statusCode} detail={r.statusDetail} />
            </td>
            <td>{r.teamName}</td>
            <td
              className="font-medium"
              style={{ color: fdr ? FDR_TEXT[fdr.pos] : "var(--muted)" }}
              title={
                fdr
                  ? `${r.position} difficulty ${fdr.pos}/5 — goals/assists ${fdr.att}/5, clean sheet ${fdr.def}/5`
                  : "no fixture"
              }
            >
              {fx ? `${fx.opp} (${fx.home ? "H" : "A"})` : "–"}
            </td>
            <td className="num">{fmt(r.price)}</td>
            <td className="num">{fmt(r.uefaForm)}</td>
            <td className="num text-[var(--muted)]">
              {hasUsableXg(r)
                ? fmt((r.xgNpxg90 ?? 0) + (r.xgXa90 ?? 0), 2)
                : "–"}
            </td>
            <td className="num">
              {(() => {
                const c = confirmedOf(r);
                const pct = c === "start" ? 100 : c === "bench" ? 0 : r.pStart != null ? Math.round(r.pStart * 100) : null;
                return (
                  <>
                    {pct != null ? `${pct}%` : "–"}
                    {c === "start" && <span className="ml-1 text-[var(--good)]" title="confirmed starting XI">✓</span>}
                    {c === "bench" && <span className="ml-1 text-[var(--muted)]" title="confirmed on the bench">⑂</span>}
                  </>
                );
              })()}
            </td>
            <td className="num">{fmt(r.expMinutes, 0)}</td>
            <td className="num font-semibold">{fmt(r.xpts)}</td>
            <td>{r.playerId === captainId ? "🅲" : r.isCaptain ? "(c)" : ""}</td>
          </tr>
          );
        })}
      </tbody>
    </table>
  );
}
