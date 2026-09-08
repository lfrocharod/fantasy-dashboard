import { EmptyState } from "@/components/ui";
import { getCurrentMatchday, getFixtureTicker } from "@/lib/ucl/queries";
import { FixtureGrid } from "./FixtureGrid";

export const dynamic = "force-dynamic";

const AHEAD = 5;

export default async function FixtureTickerPage() {
  const md = await getCurrentMatchday();
  const rows = await getFixtureTicker(md, AHEAD);

  if (rows.length === 0) {
    return (
      <EmptyState
        title="No upcoming fixtures"
        hint="Needs the fixtures table populated. Run ./run.sh on your machine."
      />
    );
  }

  const mds = Array.from({ length: AHEAD }, (_, i) => md + i).filter((m) => m <= 8);

  return <FixtureGrid rows={rows} mds={mds} />;
}
