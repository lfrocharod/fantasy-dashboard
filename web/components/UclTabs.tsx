"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/ucl", label: "Overview" },
  { href: "/ucl/players", label: "Players & FA finder" },
  { href: "/ucl/lineups", label: "Projected lineups" },
  { href: "/ucl/teams", label: "Team watch" },
  { href: "/ucl/fixtures", label: "Fixture ticker" },
  { href: "/ucl/optimizer", label: "Optimizer" },
  { href: "/ucl/rivals", label: "Rivals" },
  { href: "/ucl/league", label: "Mini-league" },
];

export function UclTabs() {
  const pathname = usePathname();
  return (
    <nav className="flex flex-wrap gap-1 border-b border-[var(--border)]">
      {TABS.map((t) => {
        const active = t.href === "/ucl" ? pathname === "/ucl" : pathname.startsWith(t.href);
        return (
          <Link
            key={t.href}
            href={t.href}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${
              active
                ? "border-[var(--accent)] text-[var(--accent)] font-medium"
                : "border-transparent text-[var(--muted)]"
            }`}
          >
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
