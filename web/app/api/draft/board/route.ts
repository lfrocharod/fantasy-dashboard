import { NextResponse } from "next/server";
import { getBoard, type Sport } from "@/lib/draft/queries";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const sport = (new URL(req.url).searchParams.get("sport") ?? "nfl") as Sport;
  const { players, picks, config } = await getBoard(sport);
  return NextResponse.json({ sport, players, picks, config });
}
