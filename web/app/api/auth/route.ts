import { NextResponse } from "next/server";
import bcrypt from "bcryptjs";
import { z } from "zod";
import { createSessionToken } from "@/lib/auth";
import { clearSessionCookie, setSessionCookie } from "@/lib/session";

export const runtime = "nodejs";

const bodySchema = z.object({ password: z.string().min(1).max(200) });

// Small fixed delay so timing doesn't leak whether the hash comparison ran.
const MIN_MS = 250;

export async function POST(req: Request) {
  const started = Date.now();
  const hash = process.env.APP_PASSWORD_HASH;
  if (!hash) {
    return NextResponse.json({ error: "server not configured" }, { status: 500 });
  }

  let password = "";
  try {
    password = bodySchema.parse(await req.json()).password;
  } catch {
    return NextResponse.json({ error: "bad request" }, { status: 400 });
  }

  const ok = await bcrypt.compare(password, hash);
  const wait = MIN_MS - (Date.now() - started);
  if (wait > 0) await new Promise((r) => setTimeout(r, wait));

  if (!ok) {
    return NextResponse.json({ error: "wrong password" }, { status: 401 });
  }

  await setSessionCookie(await createSessionToken());
  return NextResponse.json({ ok: true });
}

export async function DELETE() {
  await clearSessionCookie();
  return NextResponse.json({ ok: true });
}
