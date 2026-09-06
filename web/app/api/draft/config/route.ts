import { NextResponse } from "next/server";
import { z } from "zod";
import { getSettings, setSetting } from "@/lib/settings";
import { encryptSecret } from "@/lib/crypto";

export const runtime = "nodejs";

const sportEnum = z.enum(["nfl", "nba", "fpl"]);

export async function GET(req: Request) {
  const sport = new URL(req.url).searchParams.get("sport") ?? "nfl";
  const p = `draft.${sport}.`;
  const s = await getSettings([
    p + "league_id", p + "my_team_id", p + "my_slot", p + "teams",
    p + "scoring", p + "year", p + "espn_s2", p + "swid", p + "roster",
  ]);
  return NextResponse.json({
    sport,
    leagueId: s[p + "league_id"] ?? "",
    myTeamId: s[p + "my_team_id"] ?? "",
    mySlot: s[p + "my_slot"] ?? "",
    teams: s[p + "teams"] ?? "12",
    scoring: s[p + "scoring"] ?? "ppr",
    year: s[p + "year"] ?? "2026",
    roster: s[p + "roster"] ?? "",
    hasCookies: Boolean(s[p + "espn_s2"] && s[p + "swid"]),
  });
}

const patch = z.object({
  sport: sportEnum.default("nfl"),
  leagueId: z.string().max(32).optional(),
  myTeamId: z.coerce.number().int().min(1).max(40).optional(),
  mySlot: z.coerce.number().int().min(1).max(40).optional(),
  teams: z.coerce.number().int().min(2).max(40).optional(),
  scoring: z.enum(["ppr", "half", "standard"]).optional(),
  year: z.coerce.number().int().min(2020).max(2100).optional(),
  espnS2: z.string().min(20).max(4000).optional(),
  swid: z.string().min(8).max(200).optional(),
});

export async function POST(req: Request) {
  let b: z.infer<typeof patch>;
  try {
    b = patch.parse(await req.json());
  } catch (e) {
    return NextResponse.json({ error: "bad request", detail: String(e) }, { status: 400 });
  }
  const p = `draft.${b.sport}.`;
  const set = (key: string, v: string) => setSetting(p + key, v);

  if (b.leagueId !== undefined) await set("league_id", b.leagueId.trim());
  if (b.myTeamId !== undefined) await set("my_team_id", String(b.myTeamId));
  if (b.mySlot !== undefined) await set("my_slot", String(b.mySlot));
  if (b.teams !== undefined) await set("teams", String(b.teams));
  if (b.scoring !== undefined) await set("scoring", b.scoring);
  if (b.year !== undefined) await set("year", String(b.year));
  if (b.espnS2) await set("espn_s2", encryptSecret(b.espnS2.trim()));
  if (b.swid) await set("swid", encryptSecret(b.swid.trim()));

  return NextResponse.json({ ok: true });
}
