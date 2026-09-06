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
