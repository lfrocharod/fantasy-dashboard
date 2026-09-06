"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const res = await fetch("/api/auth", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ password }),
    });
    setBusy(false);
    if (res.ok) {
      router.replace(params.get("next") || "/");
      router.refresh();
    } else {
      setError((await res.json().catch(() => ({}))).error ?? "Login failed");
    }
  }

  return (
    <div className="mx-auto mt-24 max-w-sm">
      <div className="card p-6">
        <h1 className="text-lg font-semibold">Fantasy Dashboard</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">Enter the app password.</p>
        <form onSubmit={submit} className="mt-4 space-y-3">
          <input
            type="password"
            autoFocus
            className="input w-full"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
          />
          {error && <div className="text-sm text-[var(--bad)]">{error}</div>}
          <button type="submit" className="btn btn-primary w-full" disabled={busy}>
            {busy ? "…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}
