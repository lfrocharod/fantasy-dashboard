import { NextResponse } from "next/server";
import { getCurrentMatchday, getMySquad, getProjectedPlayers } from "@/lib/ucl/queries";
import { POSITIONS, type Position } from "@/lib/ucl/formation";

export const runtime = "nodejs";

export async function GET(req: Request) {
  const url = new URL(req.url);
  const md = Number(url.searchParams.get("matchday")) || (await getCurrentMatchday());
  const posParam = url.searchParams.get("position") as Position | null;
  const position = posParam && POSITIONS.includes(posParam) ? posParam : undefined;
  const maxPrice = url.searchParams.get("maxPrice");
  const search = url.searchParams.get("search") ?? undefined;
  const limit = Math.min(Number(url.searchParams.get("limit")) || 60, 300);

  const [rows, squad] = await Promise.all([
    getProjectedPlayers({
      matchday: md,
      position,
      maxPrice: maxPrice ? Number(maxPrice) : undefined,
      search,
      limit,
    }),
    getMySquad(md),
  ]);

  const ownedIds = squad.map((r) => r.playerId);
  return NextResponse.json({ matchday: md, count: rows.length, ownedIds, players: rows });
}
