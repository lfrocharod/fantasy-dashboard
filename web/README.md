# web

Next.js app for the Fantasy Dashboard. Deploys to Vercel with **Root Directory =
`web`**. See the [top-level README](../README.md) for the full deploy runbook.

```bash
npm install
cp .env.example .env.local     # fill in DATABASE_URL, APP_PASSWORD_HASH, SESSION_SECRET, WEB_CRYPTO_KEY
npm run db:push                # create tables in the database
npm run dev                    # http://localhost:3000
npm run hash-password 'pw'     # generate an APP_PASSWORD_HASH
```
