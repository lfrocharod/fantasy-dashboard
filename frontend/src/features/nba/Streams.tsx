import type { Api } from "@/api/client";
import { fmt, signed } from "@/shared/format";
import { SubHeading } from "@/shared/ui";
import { Who } from "./common";

/** Add/drop pairs that raise this matchup's projection. */
export function Streams({ streams }: { streams: Api["NbaStream"][] }) {
  return (
    <section className="space-y-2">
      <SubHeading>Streaming — add/drop for this matchup</SubHeading>
      <div className="card table-wrap">
        <table className="dtable">
          <thead>
            <tr>
              <th>Add</th>
              <th>Drop</th>
              <th className="num">Games</th>
              <th className="num">This matchup</th>
              <th className="num" title="rest-of-season points: what the swap costs or gains after this week">ROS</th>
            </tr>
          </thead>
          <tbody>
            {streams.map((s) => (
              <tr key={s.add.extId}>
                <td>
                  <Who p={s.add}>
                    <span className="ml-1 text-xs text-[var(--muted)]">{fmt(s.add.fppg)}/g</span>
                  </Who>
                </td>
                <td className="text-sm">
                  {s.drop.name} <span className="text-xs text-[var(--muted)]">{fmt(s.drop.fppg)}/g</span>
                </td>
                <td className="num">{s.games}</td>
                <td className="num font-semibold text-[var(--good)]">+{fmt(s.gain, 0)}</td>
                <td className="num" style={{ color: s.rosDelta < -50 ? "var(--bad)" : "var(--muted)" }}>
                  {signed(s.rosDelta, 0)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-[var(--muted)]">
        Each free agent swapped for whichever of your weakest players gains the most over the days left — lineup-aware,
        so a pickup only counts on days he'd actually start. A red ROS means the swap costs you after this week.
      </p>
    </section>
  );
}
