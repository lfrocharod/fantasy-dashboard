/** Display formatting only — every number is computed by the API. */

/** All absolute times are shown in Mexico City time. */
export const TZ = "America/Mexico_City";

export function dateTime(iso: string | Date | null | undefined): string {
  if (!iso) return "–";
  const d = typeof iso === "string" ? new Date(iso) : iso;
  if (Number.isNaN(d.getTime())) return "–";
  return d.toLocaleString("en-GB", {
    timeZone: TZ, day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false,
  });
}

export function fmt(n: number | null | undefined, digits = 1): string {
  if (n == null || !Number.isFinite(n)) return "–";
  return n.toFixed(digits);
}

export function signed(n: number | null | undefined, digits = 1): string {
  if (n == null || !Number.isFinite(n)) return "–";
  return `${n >= 0 ? "+" : ""}${n.toFixed(digits)}`;
}

export function money(n: number | null | undefined): string {
  return n == null ? "–" : `€${n.toFixed(1)}m`;
}

export function pct(n: number | null | undefined, digits = 0): string {
  return n == null ? "–" : `${(n * 100).toFixed(digits)}%`;
}

export function timeUntil(iso: string | null | undefined): string {
  if (!iso) return "–";
  const ms = new Date(iso).getTime() - Date.now();
  if (Number.isNaN(ms)) return "–";
  if (ms <= 0) return "deadline passed";
  const h = Math.floor(ms / 3.6e6);
  const d = Math.floor(h / 24);
  if (d >= 1) return `${d}d ${h % 24}h`;
  return `${h}h ${Math.floor((ms % 3.6e6) / 6e4)}m`;
}

export function relTime(iso: string | null | undefined): string {
  if (!iso) return "never";
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 6e4);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const h = Math.round(mins / 60);
  return h < 24 ? `${h}h ago` : `${Math.round(h / 24)}d ago`;
}

export const lastName = (name: string | null | undefined): string =>
  (name ?? "–").split(" ").slice(-1)[0];
