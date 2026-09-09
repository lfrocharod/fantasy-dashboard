import type { ReactNode } from "react";
import type { Position } from "@/lib/ucl/formation";

export function StatCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
}) {
  return (
    <div className="card p-4">
      <div className="text-xs uppercase tracking-wide text-[var(--muted)]">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {sub != null && <div className="mt-1 text-xs text-[var(--muted)]">{sub}</div>}
    </div>
  );
}

const POS_COLOR: Record<Position, string> = {
  GK: "#8957e5",
  DEF: "#1f6feb",
  MID: "#1a7f37",
  FWD: "#cf222e",
};

export function PosBadge({ position }: { position: Position }) {
  return (
    <span
      className="inline-block rounded px-1.5 py-0.5 text-[11px] font-semibold text-white"
      style={{ background: POS_COLOR[position] ?? "#6b7280" }}
    >
      {position}
    </span>
  );
}

export function StatusDot({ code, detail }: { code: number; detail?: string }) {
  if (!code) return null;
  const color = code >= 2 ? "var(--bad)" : "var(--warn)";
  return (
    <span title={detail || (code >= 2 ? "Out" : "Doubt")} style={{ color }}>
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

export function PageHeader({
  title,
  right,
  sub,
}: {
  title: ReactNode;
  right?: ReactNode;
  sub?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-2">
      <div>
        <h1 className="text-xl font-semibold">{title}</h1>
        {sub != null && <p className="mt-0.5 text-sm text-[var(--muted)]">{sub}</p>}
      </div>
      {right != null && <div className="text-sm text-[var(--muted)]">{right}</div>}
    </div>
  );
}

export function Loading({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      <div className="skeleton h-8 w-48" />
      <div className="card space-y-2 p-3">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="skeleton h-6 w-full" style={{ opacity: 1 - i * 0.12 }} />
        ))}
      </div>
    </div>
  );
}

export function Pill({
  children,
  tone = "muted",
}: {
  children: ReactNode;
  tone?: "good" | "warn" | "bad" | "accent" | "muted";
}) {
  const c = {
    good: "var(--good)",
    warn: "var(--warn)",
    bad: "var(--bad)",
    accent: "var(--accent)",
    muted: "var(--muted)",
  }[tone];
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
  text: ReactNode;
  href?: string;
  linkText?: string;
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
            <a href={c.href} className="ml-auto shrink-0 text-xs text-[var(--accent)]">
              {c.linkText ?? "open →"}
            </a>
          )}
        </div>
      ))}
    </div>
  );
}

/** Compact "lo–hi" outcome band, with the mean bolded when given. */
export function Range({
  lo,
  hi,
  mean,
  digits = 0,
}: {
  lo: number;
  hi: number;
  mean?: number;
  digits?: number;
}) {
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
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">{title}</h2>
        {right}
      </div>
      {children}
    </section>
  );
}
