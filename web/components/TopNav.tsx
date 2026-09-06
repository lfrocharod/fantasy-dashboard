"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

const LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/ucl", label: "Champions League" },
  { href: "/draft", label: "Draft" },
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
      <div className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3">
        <span className="font-semibold">⚽ Fantasy Dashboard</span>
        <nav className="flex gap-4 text-sm">
          {LINKS.map((l) => {
            const active = l.href === "/" ? pathname === "/" : pathname.startsWith(l.href);
            return (
              <Link
                key={l.href}
                href={l.href}
                className={active ? "text-[var(--accent)] font-medium" : "text-[var(--muted)]"}
              >
                {l.label}
              </Link>
            );
          })}
        </nav>
        <button onClick={logout} className="btn ml-auto">
          Sign out
        </button>
      </div>
    </header>
  );
}
