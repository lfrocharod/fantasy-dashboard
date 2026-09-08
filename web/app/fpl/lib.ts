import { pickFormationXI } from "@/lib/xi";

export interface GwCell {
  gw: number;
  opp: string;
  home: boolean | null;
  fdr: number; // position-aware difficulty for this player, 1 (easy) … 5 (hard)
  fdrAtt?: number; // difficulty of getting goals/assists (opponent's defensive solidity)
  fdrDef?: number; // difficulty of a clean sheet (opponent's attacking threat)
  xpts: number;
  cs: number;
}

export interface FplPlayer {
  extId: string;
  name: string;
  team: string;
  pos: string; // GKP DEF MID FWD
  proj: number; // next GW
  horizon: number; // sum over the shown GWs
  fitNext: number; // next-GW projection ignoring the injury flag
  fitHorizon: number; // 6-GW projection ignoring the injury flag
  ros: number; // rest-of-season projected points
  rosPpg: number; // ROS points per gameweek
  yellows: number;
  ycToBan: number; // bookings until the next suspension milestone
  suspRisk: boolean; // one booking from a ban
  pStart: number; // modelled probability of starting the next match
  providerRank: number; // FPL's own pre-season draft rank (1 = best)
  unavailable: boolean; // injured / suspended / <75% to play
  vbd: number;
  csProb: number;
  xgi90: number;
  gws: GwCell[];
  components: Record<string, number>;
  status: string;
  news: string;
  owner: string;
  ownerName: string;
  available: boolean; // free agent in the league
  setPiece: string;
  nextOpp: string;
  nextFdr: number;
  form: number;
  minutes: number;
  ppg: number;
  totalPoints: number;
}

export type SortKey = "horizon" | "proj" | "vbd" | "form" | "csProb" | "totalPoints";
export const POS = ["ALL", "GKP", "DEF", "MID", "FWD"] as const;
export type PosFilter = (typeof POS)[number];

export function toPlayer(p: Record<string, unknown>): FplPlayer {
  const raw = (p.raw ?? {}) as Record<string, unknown>;
  return {
    extId: String(p.extId),
    name: String(p.name),
    team: String(p.team ?? ""),
    pos: String(p.primaryPos ?? ""),
    proj: Number(p.projPoints ?? 0),
    horizon: Number(raw.horizon_xpts ?? 0),
    fitNext: Number(raw.fit_next ?? p.projPoints ?? 0),
    fitHorizon: Number(raw.fit_horizon ?? raw.horizon_xpts ?? 0),
    ros: Number(raw.ros_xpts ?? 0),
    rosPpg: Number(raw.ros_ppg ?? 0),
    yellows: Number(raw.yellows ?? 0),
    ycToBan: Number(raw.yc_to_ban ?? 5),
    suspRisk: raw.susp_risk === true,
    pStart: Number(raw.p_start ?? 0),
    providerRank: Number(p.providerRank ?? 9999),
    unavailable: raw.unavailable === true,
    vbd: Number(p.vbd ?? 0),
    csProb: Number(raw.cs_prob ?? 0),
    xgi90: Number(raw.xgi90 ?? 0),
    gws: (raw.gws as GwCell[]) ?? [],
    components: (raw.components as Record<string, number>) ?? {},
    status: String(p.injuryStatus ?? "a"),
    news: String(p.outlook ?? ""),
    owner: String(raw.owner ?? ""),
    ownerName: String(raw.owner_name ?? ""),
    available: raw.available !== false && !raw.owner,
    setPiece: String(raw.set_piece ?? ""),
    nextOpp: String(raw.next_opp ?? ""),
    nextFdr: Number(raw.next_fdr ?? 0),
    form: Number(raw.form ?? 0),
    minutes: Number(raw.minutes ?? 0),
    ppg: Number(raw.ppg ?? 0),
    totalPoints: Number(raw.total_points ?? 0),
  };
}

/** A player you'd actually claim/trade for right now: fit and expected to play. */
export function rosterable(p: FplPlayer): boolean {
  return !p.unavailable && p.status === "a";
}

export function sortPlayers(list: FplPlayer[], key: SortKey): FplPlayer[] {
  return [...list].sort((a, b) => {
    const d = Number(b[key]) - Number(a[key]);
    return d !== 0 ? d : b.horizon - a.horizon;
  });
}

const XI_MIN: Record<string, number> = { GKP: 1, DEF: 3, MID: 3, FWD: 1 };
const XI_MAX: Record<string, number> = { GKP: 1, DEF: 5, MID: 5, FWD: 3 };

/** Best legal XI by a per-cell score. No captain — draft scores every starter once. */
export function bestXI(
  squad: FplPlayer[],
  score: (p: FplPlayer) => number = (p) => p.proj,
): { xi: FplPlayer[]; bench: FplPlayer[]; formation: string } {
  const byPos: Record<string, FplPlayer[]> = { GKP: [], DEF: [], MID: [], FWD: [] };
  for (const p of squad) (byPos[p.pos] ?? (byPos[p.pos] = [])).push(p);
  for (const k of Object.keys(byPos)) byPos[k].sort((a, b) => score(b) - score(a));

  const xi: FplPlayer[] = [];
  const count: Record<string, number> = { GKP: 0, DEF: 0, MID: 0, FWD: 0 };
  for (const pos of ["GKP", "DEF", "MID", "FWD"]) {
    for (const p of byPos[pos].slice(0, XI_MIN[pos])) {
      xi.push(p);
      count[pos]++;
    }
  }
  const inXi = new Set(xi.map((p) => p.extId));
  const rest = squad
    .filter((p) => !inXi.has(p.extId) && p.pos !== "GKP")
    .sort((a, b) => score(b) - score(a));
  for (const p of rest) {
    if (xi.length >= 11) break;
    if (count[p.pos] < XI_MAX[p.pos]) {
      xi.push(p);
      count[p.pos]++;
    }
  }
  const benchIds = new Set(xi.map((p) => p.extId));
  const bench = squad
    .filter((p) => !benchIds.has(p.extId))
    .sort((a, b) => (a.pos === "GKP" ? 1 : 0) - (b.pos === "GKP" ? 1 : 0) || score(b) - score(a));
  return { xi, bench, formation: `${count.DEF}-${count.MID}-${count.FWD}` };
}

/** Total from the best XI each gameweek — no captaincy in draft. */
export function squadHorizon(squad: FplPlayer[], gwIndexes: number[]): number {
  let total = 0;
  for (const gi of gwIndexes) {
    const { xi } = bestXI(squad, (p) => p.gws[gi]?.xpts ?? 0);
    total += xi.reduce((a, p) => a + (p.gws[gi]?.xpts ?? 0), 0);
  }
  return total;
}

export interface TradeIdea {
  rivalName: string;
  give: FplPlayer[];
  get: FplPlayer[];
  myGain: number;
  theirGain: number;
}

const posKey = (ps: FplPlayer[]) =>
  ps
    .map((p) => p.pos)
    .sort()
    .join("+");

/** All size-`n` combinations of `arr`. */
function combos<T>(arr: T[], n: number): T[][] {
  if (n === 0) return [[]];
  if (arr.length < n) return [];
  const out: T[][] = [];
  const rec = (start: number, pick: T[]) => {
    if (pick.length === n) {
      out.push(pick.slice());
      return;
    }
    for (let i = start; i <= arr.length - (n - pick.length); i++) {
      pick.push(arr[i]);
      rec(i + 1, pick);
      pick.pop();
    }
  };
  rec(0, []);
  return out;
}

/**
 * Position-balanced trades of any size (1-for-1 up to `maxN`-for-`maxN`): both
 * sides must hold the same multiset of positions. Ranked by my horizon gain,
 * with the rival kept roughly whole so they'd plausibly accept. Targets are
 * limited to fit, playing players.
 */
export function tradeIdeas(
  mySquad: FplPlayer[],
  players: FplPlayer[],
  owners: Map<string, { name: string; ids: Set<string> }>,
  maxN = 4,
  h: Horizon = "medium",
): TradeIdea[] {
  const ideas: TradeIdea[] = [];
  const val = (ps: FplPlayer[]) => ps.reduce((a, p) => a + valueFor(p, h), 0);
  // realistic things to give up: my weakest ~9 (never the top of my squad)
  const givable = [...mySquad].sort((a, b) => valueFor(a, h) - valueFor(b, h)).slice(0, 9);
  const N = Math.min(maxN, givable.length);

  const giveByKey = new Map<string, FplPlayer[][]>();
  for (let n = 1; n <= N; n++)
    for (const g of combos(givable, n)) {
      const k = posKey(g);
      (giveByKey.get(k) ?? giveByKey.set(k, []).get(k)!).push(g);
    }

  for (const [entry, o] of owners) {
    const theirs = players.filter((p) => o.ids.has(p.extId) && claimable(p, h));
    if (theirs.length === 0) continue;
    for (let n = 1; n <= Math.min(N, theirs.length); n++) {
      for (const get of combos(theirs, n)) {
        const k = posKey(get);
        const gives = giveByKey.get(k);
        if (!gives) continue;
        for (const give of gives) {
          const myGain = val(get) - val(give);
          const theirGain = val(give) - val(get);
          const bar = (n === 1 ? 3 : n === 2 ? 5 : 7) * (h === "season" ? 3 : 1);
          if (myGain > bar && theirGain > -4 * (h === "season" ? 3 : 1)) {
            ideas.push({ rivalName: o.name || entry, give, get, myGain, theirGain });
          }
        }
      }
    }
  }
  // one idea per (rival, get-set) — the best give for it
  const seen = new Set<string>();
  return ideas
    .sort((a, b) => b.myGain - a.myGain || a.give.length - b.give.length)
    .filter((t) => {
      const key = t.rivalName + "|" + t.get.map((p) => p.extId).sort().join(",");
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, 12);
}

// ---- horizon-aware value -------------------------------------------------
export type Horizon = "short" | "medium" | "season";
export const HORIZON_LABEL: Record<Horizon, string> = {
  short: "next GW",
  medium: "next 6 GW",
  season: "rest of season",
};

/** The value figure to compare on for a given planning window. */
export function valueFor(p: FplPlayer, h: Horizon): number {
  return h === "short" ? p.proj : h === "medium" ? p.horizon : p.ros;
}

/** A target you'd actually claim/trade for, given how long you plan to hold. */
export function claimable(p: FplPlayer, h: Horizon): boolean {
  if (h === "short") return p.pStart >= 0.4; // just need them to feature this week
  if (!rosterable(p)) return false;
  // medium/long term: a booking away from a ban is a liability
  return !(p.suspRisk && p.ycToBan <= 1);
}

/**
 * Starters worth replacing for the chosen window: genuinely below replacement
 * level, or a real rotation/injury risk. A nailed premium at a strong club is
 * never a "weak spot" just because someone projects a hair higher.
 */
export function weakSpots(
  lineup: FplPlayer[],
  freeAgents: FplPlayer[],
  h: Horizon = "medium",
): { out: FplPlayer; in: FplPlayer; gain: number }[] {
  const fitFree = freeAgents.filter((p) => claimable(p, h));
  const val = (p: FplPlayer) => valueFor(p, h);
  const replLevel: Record<string, number> = {};
  for (const pos of ["GKP", "DEF", "MID", "FWD"]) {
    const ranked = fitFree.filter((p) => p.pos === pos).sort((a, b) => val(b) - val(a));
    replLevel[pos] = ranked[2]?.horizon ?? (ranked.at(-1) ? val(ranked.at(-1)!) : 0);
  }
  const bar = h === "short" ? 1.5 : h === "medium" ? 6 : 18;
  const out: { out: FplPlayer; in: FplPlayer; gain: number }[] = [];
  for (const s of lineup) {
    // An elite draft asset (top ~20) whose projection looks weak is almost
    // always a thin-sample artefact — a new signing, an injury returnee, a
    // player easing back to full minutes. Their ceiling dwarfs any streamer's;
    // never tell the user to waive them. (This is Barcola, Wirtz, etc.)
    if (s.providerRank && s.providerRank <= 20) continue;
    const best = fitFree.filter((p) => p.pos === s.pos).sort((a, b) => val(b) - val(a))[0];
    if (!best) continue;
    const gain = val(best) - val(s);
    const belowRepl = val(s) < (replLevel[s.pos] ?? 0) - 1;
    const risky = s.pStart > 0 && s.pStart < 0.6;
    if ((belowRepl || risky) && gain > bar) out.push({ out: s, in: best, gain });
  }
  return out.sort((a, b) => b.gain - a.gain).slice(0, 6);
}

// ---- manager rosters + trade evaluation --------------------------------
export interface Manager {
  entryId: string;
  name: string;
  isMine: boolean;
  players: FplPlayer[];
  byPos: Record<string, FplPlayer[]>;
  total: { medium: number; season: number };
}

/**
 * Group into CURRENT rosters from live ownership (`player.owner` = element-status
 * entry id), NOT the draft history. `fallbackNames` maps entry id -> team name
 * for managers whose players don't carry ownerName.
 */
export function groupByManager(
  players: FplPlayer[],
  _picks: unknown,
  myEntryId: string | null,
  fallbackNames: Record<string, string> = {},
): Manager[] {
  const m = new Map<string, Manager>();
  for (const pl of players) {
    if (!pl.owner) continue;
    const key = String(pl.owner);
    let mg = m.get(key);
    if (!mg) {
      mg = {
        entryId: key,
        name: pl.ownerName || fallbackNames[key] || `Team ${key}`,
        isMine: key === String(myEntryId),
        players: [],
        byPos: { GKP: [], DEF: [], MID: [], FWD: [] },
        total: { medium: 0, season: 0 },
      };
      m.set(key, mg);
    }
    if (pl.ownerName && (mg.name.startsWith("Team ") || !mg.name)) mg.name = pl.ownerName;
    mg.players.push(pl);
    (mg.byPos[pl.pos] ?? (mg.byPos[pl.pos] = [])).push(pl);
  }
  for (const mg of m.values()) {
    for (const k of Object.keys(mg.byPos))
      mg.byPos[k].sort((a, b) => b.horizon - a.horizon);
    mg.total.medium = round1(mg.players.reduce((a, p) => a + p.horizon, 0));
    mg.total.season = round1(mg.players.reduce((a, p) => a + p.ros, 0));
  }
  return [...m.values()].sort(
    (a, b) => (b.isMine ? 1 : 0) - (a.isMine ? 1 : 0) || b.total.season - a.total.season,
  );
}

const round1 = (n: number) => Math.round(n * 10) / 10;

export interface TradeEval {
  balanced: boolean;
  posGive: string;
  posGet: string;
  meShort: number;
  meMedium: number;
  meSeason: number;
  themShort: number;
  themMedium: number;
  themSeason: number;
  warnings: string[];
  verdict: string;
}

/** Evaluate a concrete proposed trade (any size). */
export function evaluateTrade(give: FplPlayer[], get: FplPlayer[]): TradeEval {
  const pk = (ps: FplPlayer[]) => ps.map((p) => p.pos).sort().join("+");
  const posGive = pk(give);
  const posGet = pk(get);
  const balanced = give.length === get.length && posGive === posGet;
  const sum = (ps: FplPlayer[], f: (p: FplPlayer) => number) => ps.reduce((a, p) => a + f(p), 0);
  const meShort = round1(sum(get, (p) => p.proj) - sum(give, (p) => p.proj));
  const meMedium = round1(sum(get, (p) => p.horizon) - sum(give, (p) => p.horizon));
  const meSeason = round1(sum(get, (p) => p.ros) - sum(give, (p) => p.ros));
  const warnings: string[] = [];
  for (const p of get) {
    if (p.suspRisk) warnings.push(`${p.name} is ${p.ycToBan} booking from a ban`);
    if (p.unavailable) warnings.push(`${p.name} is currently ${p.status === "s" ? "suspended" : "injured"}${p.news ? ` — ${p.news}` : ""}`);
    if (p.pStart < 0.7) warnings.push(`${p.name} isn't a nailed starter (p≈${Math.round(p.pStart * 100)}%)`);
  }
  const shortW = meShort > 0.5;
  const longW = meSeason > 3;
  const verdict = !balanced
    ? "Not position-balanced — a draft trade needs the same positions on both sides."
    : shortW && longW
      ? "Wins now and long term — propose it."
      : longW
        ? "Long-term win, roughly flat short term."
        : shortW
          ? "Short-term boost but you lose value over the season — only if you need points now."
          : meSeason < -3
            ? "You lose value both ways — don't."
            : "Marginal — roughly even.";
  return {
    balanced, posGive, posGet,
    meShort, meMedium, meSeason,
    themShort: -meShort, themMedium: -meMedium, themSeason: -meSeason,
    warnings, verdict,
  };
}

// genuinely long lay-offs (won't be back within the useful window)
const LONG_TERM_NEWS = /unknown return|out for the season|long[- ]term|acl|achilles|surgery|expected back .*(oct|nov|dec|jan)/i;
// back within a week or two
const RETURN_SOON = /expected back|late fitness test|knock|assessed|day[- ]to[- ]day/i;

/**
 * Injured players worth taking a bench spot for. In a small classic league a
 * roster slot is precious — only stash a genuine difference-maker, and only
 * wait out a *long* lay-off for a true superstar.
 */
export function stashCandidates(players: FplPlayer[], mineIds: Set<string>): FplPlayer[] {
  return players
    .filter((p) => {
      if (!p.available || mineIds.has(p.extId) || !p.unavailable) return false;
      if (p.status === "u" || p.status === "n") return false; // transferred out / not in the game
      const elite = p.providerRank <= 30 || p.fitHorizon / 6 >= 5.8;
      if (!elite) return false;
      const longTerm =
        LONG_TERM_NEWS.test(p.news) || (p.status === "i" && !RETURN_SOON.test(p.news));
      return !(longTerm && p.providerRank > 12); // only true superstars are worth a month on the bench
    })
    .sort((a, b) => a.providerRank - b.providerRank || b.fitHorizon - a.fitHorizon)
    .slice(0, 6);
}

// ---- shared board loader ---------------------------------------------------
export interface BoardData {
  players: FplPlayer[];
  picks: {
    playerExtId: string;
    teamId: number;
    teamName: string;
    isMine: boolean;
  }[];
  config: import("@/lib/draft/queries").DraftConfig | null;
}

export async function loadBoard(): Promise<BoardData> {
  const r = await fetch("/api/draft/board?sport=fpl", { cache: "no-store" });
  const d = await r.json();
  return {
    players: (d.players ?? []).map(toPlayer),
    picks: d.picks ?? [],
    config: d.config ?? null,
  };
}

// ---- fixture ticker + team watch -----------------------------------------
export interface ClubFix {
  team: string;
  cells: {
    gw: number;
    opp: string;
    home: boolean | null;
    fdr: number; // blend fallback
    fdrAtt: number; // attacking-returns difficulty (opp defence)
    fdrDef: number; // clean-sheet difficulty (opp attack)
  }[];
  avgFdr: number;
}

/** One fixture run per PL club. The per-GW cell carries both position-neutral
 * axes (fdrAtt / fdrDef) so the ticker can be viewed for attackers or defenders. */
export function clubFixtures(players: FplPlayer[]): ClubFix[] {
  const seen = new Map<string, FplPlayer>();
  for (const p of players) {
    if (!p.team || seen.has(p.team)) continue;
    if (p.gws.length) seen.set(p.team, p);
  }
  const out = [...seen.entries()].map(([team, p]) => {
    const cells = p.gws.map((g) => ({
      gw: g.gw,
      opp: g.opp.replace(/ \(.\)$/, ""),
      home: g.home,
      fdr: g.fdr,
      fdrAtt: g.fdrAtt ?? g.fdr,
      fdrDef: g.fdrDef ?? g.fdr,
    }));
    const rated = cells.filter((c) => c.fdrAtt);
    return {
      team,
      cells,
      avgFdr: rated.length ? rated.reduce((a, c) => a + c.fdrAtt, 0) / rated.length : 3,
    };
  });
  return out.sort((a, b) => a.avgFdr - b.avgFdr || a.team.localeCompare(b.team));
}

export interface ClubDossier {
  team: string;
  fixtures: ClubFix["cells"];
  avgFdr: number;
  probableXI: FplPlayer[];
  bench: FplPlayer[];
  setPieces: { pk: FplPlayer[]; fk: FplPlayer[]; ck: FplPlayer[] };
  doubts: FplPlayer[];
  keyPlayers: FplPlayer[];
}

/** Chance a player starts — modelled p_start if we have it, else a prior from ROS/GW output. */
function fplStartScore(p: FplPlayer): number {
  if (p.pStart > 0) return p.pStart;
  return Math.max(0.12, Math.min(0.7, p.rosPpg / 6));
}

/**
 * A plausible XI shaped to the club's actual formation (see lib/xi.ts): one
 * keeper, then each line sized by how many clear starters play there.
 */
function fplProbableXI(list: FplPlayer[]): [FplPlayer[], FplPlayer[]] {
  const pool = list.filter((p) => p.status === "a");
  const { xi, bench } = pickFormationXI(pool, {
    isGK: (p) => p.pos === "GKP",
    isDEF: (p) => p.pos === "DEF",
    isMID: (p) => p.pos === "MID",
    isFWD: (p) => p.pos === "FWD",
    score: fplStartScore,
  });
  return [xi, bench];
}

export function clubDossiers(players: FplPlayer[]): ClubDossier[] {
  const byTeam = new Map<string, FplPlayer[]>();
  for (const p of players) {
    if (!p.team) continue;
    (byTeam.get(p.team) ?? byTeam.set(p.team, []).get(p.team)!).push(p);
  }
  const fx = new Map(clubFixtures(players).map((c) => [c.team, c]));
  const has = (p: FplPlayer, tag: string) =>
    (p.setPiece ?? "").split(",").map((x) => x.trim()).includes(tag);
  return [...byTeam.entries()]
    .map(([team, list]) => {
      const c = fx.get(team);
      const [probableXI, bench] = fplProbableXI(list);
      return {
        team,
        fixtures: c?.cells ?? [],
        avgFdr: c?.avgFdr ?? 3,
        probableXI,
        bench,
        setPieces: {
          pk: list.filter((p) => has(p, "P")),
          fk: list.filter((p) => has(p, "F")),
          ck: list.filter((p) => has(p, "C")),
        },
        doubts: list.filter((p) => p.unavailable || p.status !== "a")
          .sort((a, b) => b.totalPoints - a.totalPoints),
        keyPlayers: [...list].sort((a, b) => b.ros - a.ros).slice(0, 5),
      };
    })
    .sort((a, b) => a.avgFdr - b.avgFdr || a.team.localeCompare(b.team));
}

export const FDR_BG_MAP: Record<number, string> = {
  1: "rgba(34,197,94,0.32)",
  2: "rgba(132,204,22,0.24)",
  3: "rgba(148,163,184,0.14)",
  4: "rgba(249,115,22,0.24)",
  5: "rgba(239,68,68,0.30)",
};

// ---- predict rivals' waiver claims -------------------------------------
export interface ClaimPrediction {
  rivalName: string;
  weakPos: string;
  weakStarter: string;
  target: FplPlayer;
  gain: number;
}

export function predictClaims(
  managers: Manager[],
  players: FplPlayer[],
  myEntryId: string | null,
): ClaimPrediction[] {
  const ownedByAnyone = new Set(
    managers.flatMap((m) => m.players.map((p) => p.extId)),
  );
  const freeAgents = players.filter(
    (p) => !ownedByAnyone.has(p.extId) && p.status === "a" && !p.unavailable,
  );
  const out: ClaimPrediction[] = [];
  for (const mg of managers) {
    if (mg.isMine || mg.entryId === String(myEntryId)) continue;
    const { xi } = bestXI(mg.players, (p) => p.ros);
    // weakest starter a rival would realistically move on — not an elite asset
    // they're holding through a slow start / injury return.
    const weak = [...xi]
      .filter((p) => !(p.providerRank && p.providerRank <= 20))
      .sort((a, b) => a.ros - b.ros)[0];
    if (!weak) continue;
    const target = freeAgents
      .filter((p) => p.pos === weak.pos)
      .sort((a, b) => b.ros - a.ros)[0];
    if (target && target.ros - weak.ros > 15) {
      out.push({
        rivalName: mg.name,
        weakPos: weak.pos,
        weakStarter: weak.name,
        target,
        gain: Math.round(target.ros - weak.ros),
      });
    }
  }
  return out.sort((a, b) => b.gain - a.gain);
}
