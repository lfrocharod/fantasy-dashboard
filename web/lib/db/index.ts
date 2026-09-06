import { drizzle as drizzlePg } from "drizzle-orm/postgres-js";
import { drizzle as drizzleNeon } from "drizzle-orm/neon-http";
import { neon } from "@neondatabase/serverless";
import postgres from "postgres";
import * as schema from "./schema";

/**
 * One client for two worlds:
 *  - Neon HTTP driver on Vercel (no pooled TCP sockets to leak in serverless).
 *  - postgres.js for local dev against a plain Postgres in Docker.
 * Selection is by URL host so nothing needs configuring per environment.
 */

const url = process.env.DATABASE_URL;
if (!url) {
  throw new Error("DATABASE_URL is not set");
}

const isNeonHttp =
  /neon\.tech/.test(url) && !process.env.FORCE_PG_DRIVER;

type DB =
  | ReturnType<typeof drizzleNeon<typeof schema>>
  | ReturnType<typeof drizzlePg<typeof schema>>;

function make(): DB {
  if (isNeonHttp) {
    return drizzleNeon(neon(url!), { schema });
  }
  const client = postgres(url!, { max: 1, prepare: false });
  return drizzlePg(client, { schema });
}

// Reuse across hot-reloads / lambda invocations.
const g = globalThis as unknown as { __db?: DB };
export const db: DB = g.__db ?? make();
if (process.env.NODE_ENV !== "production") g.__db = db;

export { schema };
