import { describe, expect, it } from "vitest";
import { fillRoster, matchesPos, myPickNumbers, rosterNeeds, sortBoard, withTierBreaks, type BoardPlayer } from "./draftBoard";

const player = (extId: string, primaryPos: string, over: Partial<BoardPlayer> = {}): BoardPlayer => ({
  extId, name: extId, team: "KC", positions: primaryPos, primaryPos, projPoints: 100, adp: 50,
  providerRank: null, ecrRank: null, ecrTier: null, ecrPosRank: "", ecrStd: 0, vbd: 0, byeWeek: null,
  injuryStatus: "", outlook: "", ...over,
});

describe("snake draft pick numbers", () => {
  it("alternates direction each round", () => {
    expect(myPickNumbers(3, 10, 4)).toEqual([3, 18, 23, 38]);
    expect(myPickNumbers(10, 10, 3)).toEqual([10, 11, 30]);
    expect(myPickNumbers(1, 12, 2)).toEqual([1, 24]);
  });
});

describe("board sorting", () => {
  const a = player("a", "RB", { vbd: 40, adp: 12, ecrRank: 10 });
  const b = player("b", "WR", { vbd: 55, adp: 20, ecrRank: 8 });
  const c = player("c", "TE", { vbd: 55, adp: 5, ecrRank: null });
  it("ranks value descending, ties by expert rank", () => {
    expect(sortBoard([a, b, c], "vbd").map((p) => p.extId)).toEqual(["b", "c", "a"]);
  });
  it("ranks ADP and expert rank ascending, missing ranks last", () => {
    expect(sortBoard([a, b, c], "adp").map((p) => p.extId)).toEqual(["c", "a", "b"]);
    expect(sortBoard([a, b, c], "ecrRank").map((p) => p.extId)).toEqual(["b", "a", "c"]);
  });
});

describe("position filter", () => {
  it("treats FLEX as RB/WR/TE and honours secondary positions", () => {
    expect(matchesPos(player("x", "TE"), "FLEX")).toBe(true);
    expect(matchesPos(player("x", "QB"), "FLEX")).toBe(false);
    expect(matchesPos(player("x", "RB", { positions: "RB,WR" }), "WR")).toBe(true);
  });
});

describe("roster fill", () => {
  const roster = { QB: 1, RB: 2, WR: 2, FLEX: 1, BE: 2 };
  it("fills starters first, overflow to FLEX then the bench", () => {
    const mine = [player("r1", "RB"), player("r2", "RB"), player("r3", "RB"), player("q1", "QB"), player("q2", "QB")];
    const filled = fillRoster(mine, roster);
    const at = (slot: string) => filled.find((r) => r.slot === slot)?.players.map((p) => p.extId);
    expect(at("RB")).toEqual(["r1", "r2"]);
    expect(at("FLEX")).toEqual(["r3"]);
    expect(at("BE")).toEqual(["q2"]);
    expect(rosterNeeds(filled)).toEqual({ WR: 2 });
  });
});

describe("tier breaks", () => {
  it("flags the first player of each tier, skipping untiered rows", () => {
    const rows = [player("a", "RB", { ecrTier: 1 }), player("b", "RB", { ecrTier: 1 }), player("c", "RB"),
      player("d", "RB", { ecrTier: 2 })];
    expect(withTierBreaks(rows).map((r) => r.tierBreak)).toEqual([true, false, false, true]);
  });
});
