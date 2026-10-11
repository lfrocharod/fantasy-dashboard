#!/usr/bin/env bash
# One-time Google Cloud setup for fantasy-dashboard. Idempotent — re-run it to
# rotate a secret or after changing a flag.
#
#   gcloud auth login
#   infra/gcp/bootstrap.sh --project MY_PROJECT --secrets-from ~/fantasy-dashboard/web/.env.local
#
# Creates, in that project:
#   * an Artifact Registry Docker repo (with a cleanup policy, so it stays free)
#   * two service accounts — fantasy-runtime (what Cloud Run runs as: may read
#     the app's secrets, nothing else) and fantasy-deployer (what GitHub Actions
#     acts as: may deploy Cloud Run and push images)
#   * Workload Identity Federation so ONLY the main branch of this repo can act
#     as fantasy-deployer — no service-account keys anywhere
#   * the app's secrets in Secret Manager, read from a KEY=VALUE file
#   * the GitHub repo variables .github/workflows/deploy.yml reads
#
# Region defaults to us-east5 (Columbus, Ohio): next door to the Neon database
# in AWS us-east-2, which matters more than distance to the browser.
set -euo pipefail

PROJECT=""
REGION=us-east5
SECRETS_FROM=""
DEMO_DATABASE_URL=""
REPO=${GITHUB_REPOSITORY:-}

usage() { sed -n '2,20p' "$0"; exit "${1:-0}"; }
while [ $# -gt 0 ]; do
  case $1 in
    --project) PROJECT=$2; shift 2 ;;
    --region) REGION=$2; shift 2 ;;
    --secrets-from) SECRETS_FROM=$2; shift 2 ;;
    --demo-database-url) DEMO_DATABASE_URL=$2; shift 2 ;;
    --repo) REPO=$2; shift 2 ;;
    -h|--help) usage ;;
    *) echo "unknown argument: $1" >&2; usage 2 ;;
  esac
done
[ -n "$PROJECT" ] || { echo "--project is required" >&2; usage 2; }
for cmd in gcloud gh; do command -v "$cmd" >/dev/null || { echo "missing: $cmd" >&2; exit 1; }; done
[ -n "$REPO" ] || REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
quiet() { "$@" --quiet >/dev/null; }

gcloud config set project "$PROJECT" --quiet >/dev/null
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT" --format 'value(projectNumber)')
RUNTIME=fantasy-runtime@$PROJECT.iam.gserviceaccount.com
DEPLOYER=fantasy-deployer@$PROJECT.iam.gserviceaccount.com
POOL=projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github

say "enabling APIs (needs billing on the project)"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com iam.googleapis.com iamcredentials.googleapis.com sts.googleapis.com

say "Artifact Registry: $REGION/fantasy"
if ! gcloud artifacts repositories describe fantasy --location "$REGION" >/dev/null 2>&1; then
  gcloud artifacts repositories create fantasy --location "$REGION" \
    --repository-format docker --description "fantasy-dashboard images"
fi
policy=$(mktemp)
trap 'rm -f "$policy"' EXIT
cat > "$policy" <<'JSON'
[
  {"name": "keep-recent", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": 5}},
  {"name": "delete-old", "action": {"type": "Delete"}, "condition": {"olderThan": "14d"}}
]
JSON
quiet gcloud artifacts repositories set-cleanup-policies fantasy --location "$REGION" \
  --policy "$policy" --no-dry-run

say "service accounts"
for sa in "fantasy-runtime:Cloud Run runtime" "fantasy-deployer:GitHub Actions deploys"; do
  name=${sa%%:*}
  if ! gcloud iam service-accounts describe "$name@$PROJECT.iam.gserviceaccount.com" >/dev/null 2>&1; then
    gcloud iam service-accounts create "$name" --display-name "fantasy-dashboard: ${sa#*:}"
  fi
done
for role in roles/run.admin roles/artifactregistry.writer; do
  quiet gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$DEPLOYER" \
    --role "$role" --condition None
done
# the deployer may launch services/jobs that run as the runtime account, nothing more
quiet gcloud iam service-accounts add-iam-policy-binding "$RUNTIME" \
  --member "serviceAccount:$DEPLOYER" --role roles/iam.serviceAccountUser

say "Workload Identity Federation: $REPO@main → fantasy-deployer"
if ! gcloud iam workload-identity-pools describe github --location global >/dev/null 2>&1; then
  gcloud iam workload-identity-pools create github --location global --display-name "GitHub Actions"
fi
if ! gcloud iam workload-identity-pools providers describe fantasy --location global \
    --workload-identity-pool github >/dev/null 2>&1; then
  gcloud iam workload-identity-pools providers create-oidc fantasy --location global \
    --workload-identity-pool github --display-name "fantasy-dashboard" \
    --issuer-uri https://token.actions.githubusercontent.com \
    --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
    --attribute-condition "assertion.repository == '$REPO' && assertion.ref == 'refs/heads/main'"
fi
quiet gcloud iam service-accounts add-iam-policy-binding "$DEPLOYER" \
  --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/$POOL/attribute.repository/$REPO"

put_secret() {  # put_secret NAME VALUE — adds a version only when the value changed
  local name=$1 value=$2
  if ! gcloud secrets describe "$name" >/dev/null 2>&1; then
    quiet gcloud secrets create "$name" --replication-policy automatic
  fi
  if [ "$(gcloud secrets versions access latest --secret "$name" 2>/dev/null || true)" != "$value" ]; then
    printf '%s' "$value" | quiet gcloud secrets versions add "$name" --data-file=-
    echo "   $name: new version"
  else
    echo "   $name: unchanged"
  fi
  quiet gcloud secrets add-iam-policy-binding "$name" \
    --member "serviceAccount:$RUNTIME" --role roles/secretmanager.secretAccessor
}
read_key() {  # read_key FILE KEY — last KEY=value in FILE, surrounding quotes stripped
  sed -n "s/^$2=//p" "$1" | tail -n 1 | sed -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'\$/\1/"
}

if [ -n "$SECRETS_FROM" ]; then
  say "secrets from $SECRETS_FROM"
  for pair in DATABASE_URL:fantasy-database-url SESSION_SECRET:fantasy-session-secret \
              APP_PASSWORD_HASH:fantasy-app-password-hash WEB_CRYPTO_KEY:fantasy-web-crypto-key; do
    key=${pair%%:*}
    value=$(read_key "$SECRETS_FROM" "$key")
    [ -n "$value" ] || { echo "!! $key is missing from $SECRETS_FROM" >&2; exit 1; }
    put_secret "${pair#*:}" "$value"
  done
else
  say "secrets: skipped (pass --secrets-from FILE to set them)"
fi
if [ -n "$DEMO_DATABASE_URL" ]; then
  say "demo database secret"
  put_secret fantasy-demo-database-url "$DEMO_DATABASE_URL"
  gh variable set DEMO_ENABLED --repo "$REPO" --body true
fi

say "GitHub variables on $REPO"
gh variable set GCP_PROJECT_ID --repo "$REPO" --body "$PROJECT"
gh variable set GCP_REGION --repo "$REPO" --body "$REGION"
gh variable set GCP_WIF_PROVIDER --repo "$REPO" --body "$POOL/providers/fantasy"
gh variable set GCP_DEPLOY_SA --repo "$REPO" --body "$DEPLOYER"
gh variable set GCP_RUNTIME_SA --repo "$REPO" --body "$RUNTIME"

say "done"
cat <<MSG
Next: merge to main (or run the Deploy workflow by hand) — it builds the images,
migrates the database and deploys the service. Then:
  gcloud run services describe fantasy --region $REGION --format 'value(status.url)'
MSG
