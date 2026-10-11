import { createBrowserRouter, type RouteObject } from "react-router";
import LoginPage from "@/features/auth/LoginPage";
import { Layout } from "@/shared/Layout";

// Each league is its own chunk, loaded on first visit.
const lazy = (load: () => Promise<{ default: React.ComponentType }>) => async () => ({
  Component: (await load()).default,
});

const ucl: RouteObject = {
  path: "ucl",
  lazy: lazy(() => import("@/features/ucl/UclLayout")),
  children: [
    { index: true, lazy: lazy(() => import("@/features/ucl/OverviewPage")) },
    { path: "players", lazy: lazy(() => import("@/features/ucl/PlayersPage")) },
    { path: "teams", lazy: lazy(() => import("@/features/ucl/TeamsPage")) },
    { path: "fixtures", lazy: lazy(() => import("@/features/ucl/FixturesPage")) },
    { path: "optimizer", lazy: lazy(() => import("@/features/ucl/OptimizerPage")) },
    { path: "rivals", lazy: lazy(() => import("@/features/ucl/RivalsPage")) },
    { path: "league", lazy: lazy(() => import("@/features/ucl/LeaguePage")) },
  ],
};

const fpl: RouteObject = {
  path: "fpl",
  lazy: lazy(() => import("@/features/fpl/FplLayout")),
  children: [
    { index: true, lazy: lazy(() => import("@/features/fpl/OverviewPage")) },
    { path: "players", lazy: lazy(() => import("@/features/fpl/PlayersPage")) },
    { path: "teams", lazy: lazy(() => import("@/features/fpl/TeamsPage")) },
    { path: "fixtures", lazy: lazy(() => import("@/features/fpl/FixturesPage")) },
    { path: "optimizer", lazy: lazy(() => import("@/features/fpl/OptimizerPage")) },
    { path: "rivals", lazy: lazy(() => import("@/features/fpl/RivalsPage")) },
    { path: "standings", lazy: lazy(() => import("@/features/fpl/StandingsPage")) },
    { path: "trade", lazy: lazy(() => import("@/features/fpl/TradePage")) },
  ],
};

const nfl: RouteObject = {
  path: "nfl",
  lazy: lazy(() => import("@/features/nfl/NflLayout")),
  children: [
    { index: true, lazy: lazy(() => import("@/features/nfl/OverviewPage")) },
    { path: "players", lazy: lazy(() => import("@/features/nfl/PlayersPage")) },
    { path: "teams", lazy: lazy(() => import("@/features/nfl/TeamsPage")) },
    { path: "fixtures", lazy: lazy(() => import("@/features/nfl/FixturesPage")) },
    { path: "optimizer", lazy: lazy(() => import("@/features/nfl/OptimizerPage")) },
    { path: "rivals", lazy: lazy(() => import("@/features/nfl/RivalsPage")) },
    { path: "standings", lazy: lazy(() => import("@/features/nfl/StandingsPage")) },
    { path: "trade", lazy: lazy(() => import("@/features/nfl/TradePage")) },
    { path: "draft", lazy: lazy(() => import("@/features/nfl/DraftBoardPage")) },
  ],
};

const nba: RouteObject = {
  path: "nba",
  lazy: lazy(() => import("@/features/nba/NbaLayout")),
  children: [
    { index: true, lazy: lazy(() => import("@/features/nba/OverviewPage")) },
    { path: "lineup", lazy: lazy(() => import("@/features/nba/LineupPage")) },
    { path: "players", lazy: lazy(() => import("@/features/nba/PlayersPage")) },
    { path: "schedule", lazy: lazy(() => import("@/features/nba/SchedulePage")) },
    { path: "standings", lazy: lazy(() => import("@/features/nba/StandingsPage")) },
    { path: "rivals", lazy: lazy(() => import("@/features/nba/RivalsPage")) },
    { path: "trade", lazy: lazy(() => import("@/features/nba/TradePage")) },
  ],
};

export const routes: RouteObject[] = [
  { path: "/login", Component: LoginPage },
  {
    path: "/",
    Component: Layout,
    children: [
      { index: true, lazy: lazy(() => import("@/features/home/HomePage")) },
      { path: "settings", lazy: lazy(() => import("@/features/settings/SettingsPage")) },
      ucl,
      fpl,
      nfl,
      nba,
      { path: "*", lazy: lazy(() => import("@/features/home/NotFoundPage")) },
    ],
  },
];

export const router = createBrowserRouter(routes);
