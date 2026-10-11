import { describe, expect, it } from "vitest";
import { dayLabel, parseEspnTeamUrl } from "./common";

describe("parseEspnTeamUrl", () => {
  it("reads the league, team and season from a team page URL", () => {
    const url = "https://fantasy.espn.com/basketball/team?leagueId=123&teamId=4&seasonId=2027";
    expect(parseEspnTeamUrl(url)).toEqual({ leagueId: "123", teamId: "4", seasonId: "2027" });
  });

  it("leaves out what isn't there", () => {
    expect(parseEspnTeamUrl("https://fantasy.espn.com/basketball/league?leagueId=9")).toEqual({
      leagueId: "9",
      teamId: undefined,
      seasonId: undefined,
    });
  });
});

describe("dayLabel", () => {
  it("shows a calendar date without shifting the day", () => {
    expect(dayLabel("2026-10-20")).toBe("Tue, Oct 20");
    expect(dayLabel(null)).toBe("–");
  });
});
