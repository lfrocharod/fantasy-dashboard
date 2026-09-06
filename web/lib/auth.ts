import { SignJWT, jwtVerify } from "jose";

/**
 * Pure JWT helpers — safe to import from middleware (Edge runtime). Anything that
 * touches `next/headers` lives in lib/session.ts instead.
 *
 * Single-user model: one shared password whose bcrypt hash is APP_PASSWORD_HASH.
 * A successful check mints this token; middleware verifies it on every request.
 */

export const SESSION_COOKIE = "fd_session";
export const MAX_AGE_SECONDS = 60 * 60 * 24 * 30; // 30 days

function secret(): Uint8Array {
  const s = process.env.SESSION_SECRET;
  if (!s || s.length < 16) {
    throw new Error("SESSION_SECRET must be set (>= 16 chars)");
  }
  return new TextEncoder().encode(s);
}

export async function createSessionToken(): Promise<string> {
  return new SignJWT({ ok: true })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime(`${MAX_AGE_SECONDS}s`)
    .sign(secret());
}

export async function verifySessionToken(token: string | undefined): Promise<boolean> {
  if (!token) return false;
  try {
    await jwtVerify(token, secret());
    return true;
  } catch {
    return false;
  }
}
