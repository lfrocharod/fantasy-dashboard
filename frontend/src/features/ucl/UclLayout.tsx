import { Link, Outlet } from "react-router";
import { LeagueTabs } from "@/shared/Layout";

const TABS: [string, string][] = [
  ["", "Overview"],
  ["players", "Players & FA"],
  ["teams", "Team watch"],
  ["fixtures", "Fixture ticker"],
  ["optimizer", "Optimizer"],
  ["rivals", "Rivals"],
  ["league", "League"],
];

export default function UclLayout() {
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Champions League Fantasy</h1>
        <Link to="/settings" className="text-sm text-[var(--muted)]">
          Settings
        </Link>
      </div>
      <LeagueTabs base="/ucl" tabs={TABS} />
      <Outlet />
    </div>
  );
}
