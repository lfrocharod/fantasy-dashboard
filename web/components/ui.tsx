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
    <dl className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--muted)]">
      {items.map(([term, meaning]) => (
        <div key={term} className="flex gap-1">
          <dt className="font-semibold text-[var(--text)]">{term}</dt>
          <dd>{meaning}</dd>
        </div>
      ))}
    </dl>
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
