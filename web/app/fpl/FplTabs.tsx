"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/fpl", label: "Overview" },
  { href: "/fpl/players", label: "Players & FA" },
  { href: "/fpl/teams", label: "Team watch" },
  { href: "/fpl/fixtures", label: "Fixture ticker" },
  { href: "/fpl/optimizer", label: "Optimizer" },
  { href: "/fpl/rivals", label: "Rivals" },
  { href: "/fpl/standings", label: "League" },
  { href: "/fpl/trade", label: "Trade" },
];

export function FplTabs() {
  const pathname = usePathname();
  return (
    <nav className="flex flex-wrap gap-1 border-b border-[var(--border)]">
      {TABS.map((t) => {
        const active = t.href === "/fpl" ? pathname === "/fpl" : pathname.startsWith(t.href);
        return (
          <Link
            key={t.href}
            href={t.href}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${
              active
                ? "border-[var(--accent)] font-medium text-[var(--accent)]"
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
