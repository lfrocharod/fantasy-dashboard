import { Outlet } from "react-router";
import { LeagueTabs } from "@/shared/Layout";

const TABS: [string, string][] = [
  ["", "Overview"],
  ["players", "Players & FA"],
  ["teams", "Team watch"],
  ["fixtures", "Fixture ticker"],
  ["optimizer", "Optimizer"],
  ["rivals", "Rivals"],
  ["standings", "League"],
  ["trade", "Trade"],
];

export default function FplLayout() {
  return (
    <div className="space-y-4">
      <LeagueTabs base="/fpl" tabs={TABS} />
      <Outlet />
    </div>
  );
}
