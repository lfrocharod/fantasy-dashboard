"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

const LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/ucl", label: "Champions League", short: "UCL" },
  { href: "/fpl", label: "FPL Draft", short: "FPL" },
  { href: "/nfl", label: "NFL", short: "NFL" },
  { href: "/nba", label: "NBA", short: "NBA" },
  { href: "/settings", label: "Settings" },
];

export function TopNav() {
  const pathname = usePathname();
  const router = useRouter();

  async function logout() {
    await fetch("/api/auth", { method: "DELETE" });
    router.replace("/login");
  }

  if (pathname === "/login") return null;

  return (
    <header className="border-b border-[var(--border)] bg-[var(--surface)]">
      <div className="mx-auto flex max-w-6xl items-center gap-2 px-3 py-2.5 sm:gap-6 sm:px-4">
        <span className="shrink-0 font-semibold">
          <span aria-hidden>⚽</span>
          <span className="ml-1 hidden sm:inline">Fantasy Dashboard</span>
        </span>
        <nav className="-mx-1 flex min-w-0 flex-1 gap-3 overflow-x-auto px-1 text-sm">
          {LINKS.map((l) => {
            const active = l.href === "/" ? pathname === "/" : pathname.startsWith(l.href);
            return (
              <Link
                key={l.href}
                href={l.href}
                className={`shrink-0 whitespace-nowrap ${
                  active ? "font-medium text-[var(--accent)]" : "text-[var(--muted)]"
                }`}
              >
                <span className="sm:hidden">{l.short ?? l.label}</span>
                <span className="hidden sm:inline">{l.label}</span>
              </Link>
            );
          })}
        </nav>
        <button onClick={logout} className="btn shrink-0 !px-2 !py-1 text-xs sm:!px-3 sm:!py-1.5 sm:text-sm">
          Sign out
        </button>
      </div>
    </header>
  );
}
