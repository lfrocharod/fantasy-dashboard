import { NextResponse } from "next/server";
import { z } from "zod";
import {
  addManualPick,
  resetPicks,
  undoLastManualPick,
  type Sport,
} from "@/lib/draft/queries";

export const runtime = "nodejs";

const postSchema = z.object({
  sport: z.enum(["nfl", "nba", "fpl"]).default("nfl"),
  extId: z.string().min(1),
  isMine: z.boolean().optional(),
  teamId: z.coerce.number().int().optional(),
  teamName: z.string().max(60).optional(),
});

export async function POST(req: Request) {
  let body: z.infer<typeof postSchema>;
  try {
    body = postSchema.parse(await req.json());
  } catch (e) {
    return NextResponse.json({ error: "bad request", detail: String(e) }, { status: 400 });
  }
  const overall = await addManualPick(body.sport, body.extId, body);
  return NextResponse.json({ ok: true, overall });
}

export async function DELETE(req: Request) {
  const url = new URL(req.url);
  const sport = (url.searchParams.get("sport") ?? "nfl") as Sport;
  if (url.searchParams.get("all") === "1") {
    await resetPicks(sport);
    return NextResponse.json({ ok: true, reset: true });
  }
  const undone = await undoLastManualPick(sport);
  return NextResponse.json({ ok: undone });
}
