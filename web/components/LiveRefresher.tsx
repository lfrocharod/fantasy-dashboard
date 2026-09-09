"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * While a matchday is live, re-run the (force-dynamic) server component every
 * `intervalMs` so a cron'd `./run.sh --live` on the ingest box shows up without a
 * manual reload. Pauses when the tab is hidden. Renders nothing.
 */
export function LiveRefresher({
  intervalMs = 60_000,
  active = true,
}: {
  intervalMs?: number;
  active?: boolean;
}) {
  const router = useRouter();
  useEffect(() => {
    if (!active) return;
    const tick = () => {
      if (typeof document === "undefined" || document.visibilityState === "visible") {
        router.refresh();
      }
    };
    const id = setInterval(tick, intervalMs);
    document.addEventListener("visibilitychange", tick);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [router, intervalMs, active]);
  return null;
}
