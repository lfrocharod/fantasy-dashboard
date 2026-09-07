/** All absolute times in the app are shown in Mexico City time. */
export const TZ = "America/Mexico_City";

export function dateTime(iso: string | Date | null | undefined): string {
  if (!iso) return "–";
  const d = typeof iso === "string" ? new Date(iso) : iso;
  if (Number.isNaN(d.getTime())) return "–";
  return d.toLocaleString("en-GB", {
    timeZone: TZ,
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function dateShort(iso: string | Date | null | undefined): string {
  if (!iso) return "–";
  const d = typeof iso === "string" ? new Date(iso) : iso;
  if (Number.isNaN(d.getTime())) return "–";
  return d.toLocaleDateString("en-GB", {
    timeZone: TZ,
    weekday: "short",
    day: "2-digit",
    month: "short",
  });
}

export function fmt(n: number | null | undefined, digits = 1): string {
  if (n == null || !Number.isFinite(n)) return "–";
  return n.toFixed(digits);
}

export function money(n: number | null | undefined): string {
  if (n == null) return "–";
  return `€${n.toFixed(1)}m`;
}

export function pct(n: number | null | undefined): string {
  if (n == null) return "–";
  return `${Math.round(n)}%`;
}

export function timeUntil(iso: string | null): string {
  if (!iso) return "–";
  const ms = new Date(iso).getTime() - Date.now();
  if (Number.isNaN(ms)) return "–";
  if (ms <= 0) return "deadline passed";
  const h = Math.floor(ms / 3.6e6);
  const d = Math.floor(h / 24);
  if (d >= 1) return `${d}d ${h % 24}h`;
  const m = Math.floor((ms % 3.6e6) / 6e4);
  return `${h}h ${m}m`;
}

export function relTime(d: Date | string | null): string {
  if (!d) return "never";
  const t = typeof d === "string" ? new Date(d).getTime() : d.getTime();
  const mins = Math.round((Date.now() - t) / 6e4);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const h = Math.round(mins / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.round(h / 24)}d ago`;
}
