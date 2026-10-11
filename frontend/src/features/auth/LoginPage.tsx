import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { fetchClient } from "@/api/client";

export default function LoginPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const qc = useQueryClient();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const { error: err, response } = await fetchClient.POST("/api/auth", { body: { password } });
    setBusy(false);
    if (response.ok) {
      await qc.invalidateQueries();
      const next = params.get("next");
      navigate(next && next.startsWith("/") ? next : "/", { replace: true });
    } else {
      const detail = (err as { detail?: unknown } | undefined)?.detail;
      setError(typeof detail === "string" ? detail : "Login failed");
    }
  }

  return (
    <div className="mx-auto mt-24 max-w-sm px-4">
      <div className="card p-6">
        <h1 className="text-lg font-semibold">Fantasy Dashboard</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">Enter the app password.</p>
        <form onSubmit={submit} className="mt-4 space-y-3">
          <input
            type="password"
            autoFocus
            autoComplete="current-password"
            className="input w-full"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            aria-label="Password"
          />
          {error && <div className="text-sm text-[var(--bad)]">{error}</div>}
          <button type="submit" className="btn btn-primary w-full" disabled={busy || !password}>
            {busy ? "…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
