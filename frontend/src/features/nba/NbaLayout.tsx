import { Outlet } from "react-router";
import { LeagueTabs } from "@/shared/Layout";

const TABS: [string, string][] = [
  ["", "Overview"],
  ["lineup", "Lineup"],
  ["players", "Players & FA"],
  ["schedule", "Schedule"],
  ["standings", "League"],
  ["rivals", "Rivals"],
  ["trade", "Trade"],
];

export default function NbaLayout() {
  return (
    <div className="space-y-4">
      <LeagueTabs base="/nba" tabs={TABS} />
      <Outlet />
    </div>
  );
}
