"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/nfl", label: "Lineup" },
  { href: "/nfl/waivers", label: "Waivers" },
  { href: "/nfl/trade", label: "Trade" },
  { href: "/nfl/teams", label: "Team watch" },
  { href: "/nfl/fixtures", label: "Fixture ticker" },
  { href: "/nfl/planner", label: "Bye / playoffs" },
  { href: "/nfl/draft", label: "Draft board" },
];

export function NflTabs() {
  const pathname = usePathname();
  return (
    <nav className="flex flex-wrap gap-1 border-b border-[var(--border)]">
      {TABS.map((t) => {
        const active = t.href === "/nfl" ? pathname === "/nfl" : pathname.startsWith(t.href);
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
