import { createCipheriv, createDecipheriv, randomBytes } from "node:crypto";

/**
 * AES-256-GCM for the UEFA session token / credentials at rest in the `settings`
 * table. WEB_CRYPTO_KEY is 32 raw bytes, base64-encoded. The Python ingestion
 * job uses the same scheme (see ingest/fantasy_ingest/secretbox.py).
 *
 * Encoded form: base64(iv[12] || tag[16] || ciphertext), prefixed "v1:".
 */

const PREFIX = "v1:";

function key(): Buffer {
  const raw = process.env.WEB_CRYPTO_KEY;
  if (!raw) throw new Error("WEB_CRYPTO_KEY is not set");
  const buf = Buffer.from(raw, "base64");
  if (buf.length !== 32) {
    throw new Error("WEB_CRYPTO_KEY must decode to 32 bytes (base64)");
  }
  return buf;
}

export function encryptSecret(plaintext: string): string {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key(), iv);
  const enc = Buffer.concat([cipher.update(plaintext, "utf8"), cipher.final()]);
  const tag = cipher.getAuthTag();
  return PREFIX + Buffer.concat([iv, tag, enc]).toString("base64");
}

export function decryptSecret(payload: string): string {
  if (!payload.startsWith(PREFIX)) {
    throw new Error("unrecognised secret payload");
  }
  const buf = Buffer.from(payload.slice(PREFIX.length), "base64");
  const iv = buf.subarray(0, 12);
  const tag = buf.subarray(12, 28);
  const enc = buf.subarray(28);
  const decipher = createDecipheriv("aes-256-gcm", key(), iv);
  decipher.setAuthTag(tag);
  return Buffer.concat([decipher.update(enc), decipher.final()]).toString("utf8");
}
