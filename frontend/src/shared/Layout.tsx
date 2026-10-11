import { useQueryClient } from "@tanstack/react-query";
import { Link, NavLink, Navigate, Outlet, useLocation, useNavigate } from "react-router";
import { $api, fetchClient } from "@/api/client";
import { Loading } from "./ui";

const LINKS = [
  { to: "/", label: "Home", short: "Home", end: true },
  { to: "/ucl", label: "Champions League", short: "UCL", end: false },
  { to: "/fpl", label: "FPL Draft", short: "FPL", end: false },
  { to: "/nfl", label: "NFL", short: "NFL", end: false },
  { to: "/nba", label: "NBA", short: "NBA", end: false },
  { to: "/settings", label: "Settings", short: "Settings", end: false },
];

function TopNav({ demo }: { demo: boolean }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  async function logout() {
    await fetchClient.DELETE("/api/auth");
    qc.clear();
    navigate("/login", { replace: true });
  }
  return (
    <header className="border-b border-[var(--border)] bg-[var(--surface)]">
      <div className="mx-auto flex max-w-6xl items-center gap-2 px-3 py-2.5 sm:gap-6 sm:px-4">
        <Link to="/" className="shrink-0 font-semibold">
          <span aria-hidden>⚽</span>
          <span className="ml-1 hidden sm:inline">Fantasy Dashboard</span>
        </Link>
        <nav className="-mx-1 flex min-w-0 flex-1 gap-3 overflow-x-auto px-1 text-sm">
          {LINKS.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.end}
              className={({ isActive }) =>
                `shrink-0 whitespace-nowrap ${isActive ? "font-medium text-[var(--accent)]" : "text-[var(--muted)]"}`
              }
            >
              <span className="sm:hidden">{l.short}</span>
              <span className="hidden sm:inline">{l.label}</span>
            </NavLink>
          ))}
        </nav>
        {!demo && (
          <button onClick={logout} className="btn shrink-0 !px-2 !py-1 text-xs sm:!px-3 sm:!py-1.5 sm:text-sm">
            Sign out
          </button>
        )}
      </div>
    </header>
  );
}

function DemoBanner() {
  return (
    <div className="border-b border-[var(--border)] bg-[color-mix(in_srgb,var(--accent)_10%,transparent)] px-4 py-2 text-center text-xs">
      <b>Live demo</b> — anonymised sample leagues, read-only. Real public player data (UEFA sample feeds,
      FPL, nflverse, ESPN); every manager and team name is made up.{" "}
      <a className="text-[var(--accent)] underline" href="https://github.com/lfrocharod/fantasy-dashboard">
        Source on GitHub
      </a>
    </div>
  );
}

/** App shell: requires a session (or the public demo), then renders the page. */
export function Layout() {
  const session = $api.useQuery("get", "/api/session", {}, { staleTime: 5 * 60_000 });
  const location = useLocation();
  if (session.isPending) return <Loading rows={3} />;
  if (!session.data?.authenticated) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return (
    <>
      {session.data.demo && <DemoBanner />}
      <TopNav demo={session.data.demo} />
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </>
  );
}

/** Tabs inside a league (Overview, Players & FA, Team watch, …). */
export function LeagueTabs({ base, tabs }: { base: string; tabs: [string, string][] }) {
  return (
    <nav className="flex flex-wrap gap-1 border-b border-[var(--border)]" aria-label="sections">
      {tabs.map(([path, label]) => (
        <NavLink
          key={path}
          to={path ? `${base}/${path}` : base}
          end={!path}
          className={({ isActive }) =>
            `-mb-px border-b-2 px-3 py-2 text-sm ${
              isActive
                ? "border-[var(--accent)] font-medium text-[var(--accent)]"
                : "border-transparent text-[var(--muted)]"
            }`
          }
        >
          {label}
        </NavLink>
      ))}
    </nav>
  );
}
