// Shared xG-sample thresholds — pure, no server imports, safe for client
// components. Kept in step with `_MIN_XG_MINUTES` in
// ingest/fantasy_ingest/model/projections.py: below this bar the projection
// model DROPS a matched xG stat as an unreliable sample / likely bad identity
// match, so the UI must not show an xGI/90 rate the model isn't trusting.

export const XG_MIN_MINUTES = 200;
export const XG_MIN_MATCHES = 3;

export function hasUsableXg(p: {
  xgMatches: number | null;
  xgMinutes: number | null;
}): boolean {
  return (p.xgMatches ?? 0) >= XG_MIN_MATCHES && (p.xgMinutes ?? 0) >= XG_MIN_MINUTES;
}
