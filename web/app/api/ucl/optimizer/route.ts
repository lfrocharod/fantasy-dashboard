import { NextResponse } from "next/server";
import { getSetting, KEYS } from "@/lib/settings";

export const runtime = "nodejs";

/**
 * The optimizer runs in Python during ingestion and stashes its result as JSON.
 * Shape (see ingest/fantasy_ingest/model/optimizer.py):
 *   {
 *     generatedAt, matchday, horizon,
 *     bestXI: [{ playerId, name, position, xpts, isCaptain, isVice }],
 *     bench: [{ playerId, name, position, xpts, order }],
 *     formation: "4-4-2",
 *     baselineXpts, optimisedXpts,
 *     transfers: [{ out: {...}, in: {...}, netGain, hitCost, horizonGain }]
 *   }
 */
export async function GET() {
  const raw = await getSetting(KEYS.optimizerOutput);
  if (!raw) {
    return NextResponse.json({ available: false }, { status: 200 });
  }
  try {
    return NextResponse.json({ available: true, ...JSON.parse(raw) });
  } catch {
    return NextResponse.json({ available: false, error: "corrupt optimizer output" }, { status: 200 });
  }
}
