import { NextResponse } from "next/server";

export const runtime = "nodejs";

/**
 * Kick the GitHub Actions ingestion job on demand (e.g. right before a deadline).
 * Needs two env vars, otherwise this is a no-op the UI hides:
 *   GH_REPO            "owner/repo"
 *   GH_DISPATCH_TOKEN  fine-grained PAT with Actions: read/write on that repo
 */
export async function POST() {
  const repo = process.env.GH_REPO;
  const token = process.env.GH_DISPATCH_TOKEN;
  if (!repo || !token) {
    return NextResponse.json({ error: "refresh not configured" }, { status: 501 });
  }

  const res = await fetch(
    `https://api.github.com/repos/${repo}/actions/workflows/ingest.yml/dispatches`,
    {
      method: "POST",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${token}`,
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({ ref: "main" }),
    },
  );

  if (!res.ok) {
    return NextResponse.json(
      { error: "github dispatch failed", status: res.status, detail: await res.text() },
      { status: 502 },
    );
  }
  return NextResponse.json({ ok: true });
}
