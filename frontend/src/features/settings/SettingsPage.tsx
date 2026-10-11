import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";
import { $api, fetchClient, type Api } from "@/api/client";
import { dateTime } from "@/shared/format";
import { QueryView } from "@/shared/ui";

const REASON_LABEL: Record<string, string> = {
  no_name_match: "name not found in the stats source",
  no_stat_row: "matched a player, but no season row",
  low_minutes: "too few minutes to trust a rate",
  below_min_price: "skipped (cheap fringe player)",
};

export default function SettingsPage() {
  const q = $api.useQuery("get", "/api/settings/ucl");
  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="text-xl font-semibold">Settings</h1>
      <QueryView query={q}>{(cfg) => <UclSettings cfg={cfg} />}</QueryView>
      <p className="text-sm text-[var(--muted)]">
        FPL Draft and ESPN NFL are set up from their own pages (the <b>Setup</b> button on the FPL overview and
        the NFL draft board).
      </p>
    </div>
  );
}

function UclSettings({ cfg }: { cfg: Api["UclSettings"] }) {
  const qc = useQueryClient();
  const [leagueCode, setLeagueCode] = useState(cfg.leagueCode);
  const [entryId, setEntryId] = useState(cfg.entryId);
  const [matchday, setMatchday] = useState(cfg.matchdayOverride);
  const [token, setToken] = useState("");
  const [modelParams, setModelParams] = useState(cfg.modelParams);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    const { error, response } = await fetchClient.POST("/api/settings/ucl", {
      body: {
        leagueCode,
        entryId,
        modelParams,
        matchdayOverride: matchday ? Number(matchday) : 0,
        ...(token.trim() ? { uefaToken: token.trim() } : {}),
      },
    });
    setBusy(false);
    if (response.ok) {
      setMsg("Saved — the next sync picks it up.");
      setToken("");
      qc.invalidateQueries();
    } else {
      const detail = (error as { detail?: unknown } | undefined)?.detail;
      setMsg(typeof detail === "string" ? detail : "Save failed");
    }
  }

  const authColor =
    cfg.authState === "authed" ? "var(--good)" : cfg.authState === "public_only" ? "var(--warn)" : undefined;

  return (
    <>
      <div className="card p-4 text-sm">
        <div className="font-medium">UEFA connection</div>
        <div className="mt-1 text-[var(--muted)]">
          State: <b style={{ color: authColor }}>{cfg.authState}</b>
          {cfg.tokenSavedAt && <> · cookie saved {dateTime(cfg.tokenSavedAt)}</>}
        </div>
        <p className="mt-2 text-[var(--muted)]">
          Players, prices, fixtures and projections load with no login. Your squad and the mini-league table need
          your session cookie: sign in at gaming.uefa.com, open DevTools → Network, click any request to{" "}
          <code>gaming.uefa.com/.../services/api/…</code>, and under <b>Request Headers</b> copy the whole{" "}
          <code>Cookie:</code> value into the box below. It expires after a while — re-paste when the state shows{" "}
          <code>public_only</code>.
        </p>
      </div>

      <form onSubmit={save} className="card space-y-4 p-4">
        <Field label="Mini-league code" hint="e.g. DEMO42 — the code you share to invite people">
          <input className="input w-full" value={leagueCode} onChange={(e) => setLeagueCode(e.target.value)} />
        </Field>
        <Field label="Your UEFA GUID" hint="the id in any /Gameplay/user/<GUID>/… request URL">
          <input className="input w-full font-mono text-xs" value={entryId} onChange={(e) => setEntryId(e.target.value)} />
        </Field>
        <Field label="Pin a matchday" hint="leave blank to follow the game (recommended)">
          <input className="input w-32" inputMode="numeric" value={matchday} onChange={(e) => setMatchday(e.target.value)} />
        </Field>
        <Field
          label="UEFA session cookie"
          hint={cfg.hasToken ? "a cookie is stored; paste a new one to replace it" : "the full Cookie: request header value"}
        >
          <textarea
            className="input w-full font-mono text-xs"
            rows={3}
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="name1=value1; name2=value2; …"
          />
        </Field>
        <Field label="Model parameters (JSON)" hint="advanced — overrides projection weights">
          <textarea
            className="input w-full font-mono text-xs"
            rows={4}
            value={modelParams}
            onChange={(e) => setModelParams(e.target.value)}
            placeholder='{"form_weight": 0.3, "horizon": 2}'
          />
        </Field>
        <div className="flex items-center gap-3">
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? "Saving…" : "Save"}
          </button>
          {msg && <span className="text-sm text-[var(--muted)]">{msg}</span>}
        </div>
      </form>

      {cfg.xgCoverage && <XgCoverage cov={cfg.xgCoverage} />}
    </>
  );
}

function XgCoverage({ cov }: { cov: Api["XgCoverage"] }) {
  const pct = cov.total ? Math.round((cov.matched / cov.total) * 100) : 0;
  const misses = cov.notableMissing.length ? cov.notableMissing : cov.topMissing;
  return (
    <div className="card space-y-3 p-4 text-sm">
      <div className="flex items-baseline justify-between">
        <div className="font-medium">xG data coverage</div>
        <div className="text-xs text-[var(--muted)]">
          {cov.source} · {dateTime(cov.generatedAt)}
        </div>
      </div>
      <div className="text-[var(--muted)]">
        <b style={{ color: pct >= 92 ? "var(--good)" : pct >= 80 ? "var(--warn)" : "var(--bad)" }}>
          {cov.matched}/{cov.total}
        </b>{" "}
        players ({pct}%) got an underlying-stat row.{" "}
        {Object.entries(cov.byReason)
          .map(([r, n]) => `${n} ${REASON_LABEL[r] ?? r}`)
          .join(" · ")}
      </div>
      {misses.length > 0 && (
        <div className="table-wrap">
          <table className="dtable">
            <thead>
              <tr>
                <th>Player</th>
                <th>Team</th>
                <th className="num">Price</th>
                <th>Why</th>
                <th className="num">uefa id</th>
              </tr>
            </thead>
            <tbody>
              {misses.map((m) => (
                <tr key={m.id}>
                  <td>{m.name}</td>
                  <td>{m.team}</td>
                  <td className="num">{m.price.toFixed(1)}</td>
                  <td className="text-xs text-[var(--muted)]">{REASON_LABEL[m.reason] ?? m.reason}</td>
                  <td className="num font-mono text-xs">{m.id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <div className="text-sm font-medium">{label}</div>
      {hint && <div className="mb-1 text-xs text-[var(--muted)]">{hint}</div>}
      {children}
    </label>
  );
}
