import type { ReactNode } from "react";
import { Link } from "react-router";

export function StatCard({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="card p-4">
      <div className="text-xs uppercase tracking-wide text-[var(--muted)]">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {sub != null && <div className="mt-1 text-xs text-[var(--muted)]">{sub}</div>}
    </div>
  );
}

const POS_COLOR: Record<string, string> = {
  GK: "#8957e5", GKP: "#6b7280", DEF: "#1f6feb", MID: "#1a7f37", FWD: "#cf222e",
  QB: "#8957e5", RB: "#1a7f37", WR: "#1f6feb", TE: "#b7791f", K: "#6b7280", DST: "#cf222e",
  PG: "#8957e5", SG: "#1f6feb", SF: "#1a7f37", PF: "#b7791f", C: "#cf222e",
};

export function PosBadge({ position, small = false }: { position: string; small?: boolean }) {
  return (
    <span
      className={`inline-block rounded font-semibold text-white ${small ? "px-1 text-[10px]" : "px-1.5 py-0.5 text-[11px]"}`}
      style={{ background: POS_COLOR[position] ?? "#6b7280" }}
    >
      {position}
    </span>
  );
}

export function StatusDot({ code, detail }: { code: number; detail?: string }) {
  if (!code) return null;
  return (
    <span title={detail || (code >= 2 ? "Out" : "Doubt")} style={{ color: code >= 2 ? "var(--bad)" : "var(--warn)" }}>
      ●
    </span>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: ReactNode }) {
  return (
    <div className="card p-8 text-center">
      <div className="font-medium">{title}</div>
      {hint != null && <div className="mt-2 text-sm text-[var(--muted)]">{hint}</div>}
    </div>
  );
}

export function Legend({ items }: { items: [string, string][] }) {
  return (
    <details className="group text-xs text-[var(--muted)]">
      <summary className="cursor-pointer select-none list-none font-semibold text-[var(--text)]">
        <span className="group-open:hidden">▸ What the columns mean</span>
        <span className="hidden group-open:inline">▾ What the columns mean</span>
      </summary>
      <dl className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
        {items.map(([term, meaning]) => (
          <div key={term} className="flex gap-1">
            <dt className="font-semibold text-[var(--text)]">{term}</dt>
            <dd>{meaning}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

export function Loading({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-2" aria-busy="true" aria-label="loading">
      <div className="skeleton h-8 w-48" />
      <div className="card space-y-2 p-3">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="skeleton h-6 w-full" style={{ opacity: 1 - i * 0.12 }} />
        ))}
      </div>
    </div>
  );
}

type Tone = "good" | "warn" | "bad" | "accent" | "muted";
const TONE: Record<Tone, string> = {
  good: "var(--good)", warn: "var(--warn)", bad: "var(--bad)", accent: "var(--accent)", muted: "var(--muted)",
};

export function Pill({ children, tone = "muted" }: { children: ReactNode; tone?: Tone }) {
  const c = TONE[tone];
  return (
    <span
      className="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold"
      style={{ color: c, background: `color-mix(in srgb, ${c} 14%, transparent)` }}
    >
      {children}
    </span>
  );
}

export interface CheckItem {
  ok: boolean;
  text: string;
  href?: string | null;
  linkText?: string | null;
}

/** The OK / DO checklist shared by the three overview pages. */
export function Checklist({ items }: { items: CheckItem[] }) {
  return (
    <div className="card divide-y divide-[var(--border)]">
      {items.map((c, i) => (
        <div key={i} className="flex items-center gap-2 px-3 py-2 text-sm">
          <span
            className="rounded px-1.5 py-0.5 text-[10px] font-bold text-white"
            style={{ background: c.ok ? "var(--good)" : "var(--warn)" }}
          >
            {c.ok ? "OK" : "DO"}
          </span>
          <span>{c.text}</span>
          {c.href && !c.ok && (
            <Link to={c.href} className="ml-auto shrink-0 text-xs text-[var(--accent)]">
              {c.linkText ?? "open →"}
            </Link>
          )}
        </div>
      ))}
    </div>
  );
}

/** Compact "lo · mean · hi" outcome band. */
export function Range({ lo, hi, mean, digits = 0 }: { lo: number; hi: number; mean?: number | null; digits?: number }) {
  if (!(hi > 0)) return <span className="text-[var(--muted)]">–</span>;
  const f = (n: number) => n.toFixed(digits);
  return (
    <span className="tabular-nums text-xs text-[var(--muted)]">
      {f(lo)}
      {mean != null && (
        <>
          {" · "}
          <b className="text-[var(--text)]">{f(mean)}</b>
        </>
      )}
      {" · "}
      {f(hi)}
    </span>
  );
}

export function Section({ title, children, right }: { title: string; children: ReactNode; right?: ReactNode }) {
  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">{title}</h2>
        {right}
      </div>
      {children}
    </section>
  );
}

/** Small heading used inside a league page for sub-sections. */
export function SubHeading({ children }: { children: ReactNode }) {
  return <h2 className="text-sm font-semibold uppercase text-[var(--muted)]">{children}</h2>;
}

/** A row of toggle buttons (position filters, horizons, views). */
export function Toggle<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: readonly (T | readonly [T, string])[];
  onChange: (v: T) => void;
  label?: (v: T) => string;
}) {
  return (
    <div className="flex flex-wrap gap-1 text-xs" role="group">
      {options.map((o) => {
        const [v, text] = Array.isArray(o) ? (o as readonly [T, string]) : [o as T, label ? label(o as T) : (o as string)];
        return (
          <button
            key={v}
            type="button"
            onClick={() => onChange(v)}
            aria-pressed={value === v}
            className={`rounded px-2 py-1 ${value === v ? "bg-[var(--accent)] text-white" : "border border-[var(--border)]"}`}
          >
            {text}
          </button>
        );
      })}
    </div>
  );
}

/** Loading / error / empty handling for a query, so pages only render data. */
export function QueryView<T>({
  query,
  children,
  rows,
}: {
  query: { data?: T; isPending: boolean; error: unknown };
  children: (data: T) => ReactNode;
  rows?: number;
}) {
  if (query.isPending) return <Loading rows={rows} />;
  if (query.error || query.data === undefined) {
    const msg = query.error instanceof Error ? query.error.message : JSON.stringify(query.error ?? "no data");
    return <EmptyState title="Couldn't load this page" hint={<span className="text-[var(--bad)]">{msg}</span>} />;
  }
  return <>{children(query.data)}</>;
}
