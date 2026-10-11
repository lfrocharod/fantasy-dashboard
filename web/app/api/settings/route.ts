import { NextResponse } from "next/server";
import { z } from "zod";
import { getSettings, setSetting, KEYS } from "@/lib/settings";
import { encryptSecret } from "@/lib/crypto";

export const runtime = "nodejs";

/** GET: current non-secret config + whether a UEFA token is stored. */
export async function GET() {
  const s = await getSettings([
    KEYS.leagueId,
    KEYS.leagueCode,
    KEYS.entryId,
    KEYS.matchdayOverride,
    KEYS.deadline,
    KEYS.uefaAuthState,
    KEYS.uefaTokenSavedAt,
    KEYS.modelParams,
    KEYS.xgCoverage,
  ]);
  let xgCoverage: unknown = null;
  try {
    xgCoverage = s[KEYS.xgCoverage] ? JSON.parse(s[KEYS.xgCoverage]) : null;
  } catch {
    xgCoverage = null;
  }
  return NextResponse.json({
    leagueId: s[KEYS.leagueId] ?? "",
    leagueCode: s[KEYS.leagueCode] ?? "",
    entryId: s[KEYS.entryId] ?? "",
    currentMatchday: s[KEYS.matchdayOverride] ?? "",
    deadlineIso: s[KEYS.deadline] ?? "",
    authState: s[KEYS.uefaAuthState] ?? "unknown",
    tokenSavedAt: s[KEYS.uefaTokenSavedAt] ?? null,
    hasToken: Boolean(s[KEYS.uefaTokenSavedAt]),
    modelParams: s[KEYS.modelParams] ?? "",
    xgCoverage,
  });
}

const patchSchema = z.object({
  leagueId: z.string().max(64).optional(),
  leagueCode: z.string().max(32).optional(),
  entryId: z.string().max(64).optional(),
  currentMatchday: z.coerce.number().int().min(0).max(20).optional(), // 0 = clear the pin
  // Raw UEFA session token (Bearer value or cookie string). Stored encrypted.
  uefaToken: z.string().min(8).max(8000).optional(),
  modelParams: z.string().max(8000).optional(),
});

export async function POST(req: Request) {
  let body: z.infer<typeof patchSchema>;
  try {
    body = patchSchema.parse(await req.json());
  } catch (e) {
    return NextResponse.json({ error: "bad request", detail: String(e) }, { status: 400 });
  }

  if (body.leagueId !== undefined) await setSetting(KEYS.leagueId, body.leagueId.trim());
  if (body.leagueCode !== undefined)
    await setSetting(KEYS.leagueCode, body.leagueCode.trim().toUpperCase());
  if (body.entryId !== undefined) await setSetting(KEYS.entryId, body.entryId.trim());
  if (body.currentMatchday !== undefined)
    await setSetting(KEYS.matchdayOverride, body.currentMatchday ? String(body.currentMatchday) : "");
  if (body.modelParams !== undefined) await setSetting(KEYS.modelParams, body.modelParams);

  if (body.uefaToken) {
    await setSetting(KEYS.uefaToken, encryptSecret(body.uefaToken.trim()));
    await setSetting(KEYS.uefaTokenSavedAt, new Date().toISOString());
    // The next ingestion run verifies it and sets "authed" / "public_only".
    await setSetting(KEYS.uefaAuthState, "unverified");
  }

  return NextResponse.json({ ok: true });
}
