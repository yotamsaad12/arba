# Deploying Arba

The web app runs on **Vercel**. The API, its database and uploaded files run on **Railway**.
Vercel forwards every `/api/...` request to Railway, so the browser sees one site and the
login cookie keeps working.

```
browser ──> arba.vercel.app ──(static files)
                    └── /api/* ──> arba-api-production.up.railway.app ──> Postgres
```

Why not the API on Vercel too: it needs a database, files that stay after a restart, and a
worker that runs every few seconds (notifications, letters to authorities, reminders). Vercel
functions are short-lived and keep nothing.

## 1. Railway: the API and the database (once)

1. railway.com → **New Project** → **Deploy from GitHub repo** → `yotamsaad12/arba`.
2. In the new service: **Settings → Source → Root Directory** = `backend`.
   Railway then finds `backend/Dockerfile` and `backend/railway.json` by itself.
3. **Settings → Service name**: `arba-api`.
4. Project canvas → **+ Create → Database → PostgreSQL**.
5. The `arba-api` service → **+ Volume** → mount path `/data` (uploaded files live there).
6. `arba-api` → **Variables** → add:

   | Variable | Value |
   |---|---|
   | `ARBA_ENV` | `production` |
   | `ARBA_DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (Railway fills it in) |
   | `ARBA_JWT_SECRET` | a long random string: run `openssl rand -hex 32` |
   | `ARBA_INBOUND_WEBHOOK_PASSWORD` | another `openssl rand -hex 32` |
   | `ARBA_APP_URL` | your Vercel address, e.g. `https://arba.vercel.app` |
   | `ARBA_COOKIE_SECURE` | `true` |
   | `ARBA_WHATSAPP_PROVIDER` | `disabled` (until Meta is set up: [whatsapp-setup.md](whatsapp-setup.md)) |
   | `ARBA_SMTP_HOST` | `smtp.gmail.com` |
   | `ARBA_SMTP_PORT` | `587` |
   | `ARBA_SMTP_STARTTLS` | `true` |
   | `ARBA_SMTP_USER` | your Gmail address |
   | `ARBA_SMTP_PASSWORD` | the Gmail **app password** (a new one, not the one shared in chat) |
   | `ARBA_EMAIL_FROM` | `Arba <your Gmail address>` |
   | `ARBA_EMAIL_ALLOWED_RECIPIENTS` | `["your Gmail address"]` while testing: letters to authorities then come to you, marked as a test |
   | `ANTHROPIC_API_KEY` | optional: Claude reads permits and writes letters far better than the fallback rules |

7. `arba-api` → **Settings → Networking → Generate Domain**. Railway proposes
   `arba-api-production.up.railway.app`. If it gives a different address, put that address
   in `vercel.json` (the `/api` rewrite) and push.
8. Deploy. On each start the API migrates the database and loads the reference data, then
   `https://<railway address>/health` answers `{"status":"ok"}`.

## 2. Vercel: the web app

`vercel.json` at the repository root already says what to build and where the output is.
In the Vercel project → **Settings → Build and Deployment**:

- **Root Directory**: empty (the repository root).
- **Framework Preset**: Other, with every override switched **off** (`vercel.json` decides).

Then **Deployments → Redeploy**. Open the site, register, and create a project.

## When something doesn't work

- **Vercel build fails**: the build log shows the error; locally `npm ci && npm run build`
  reproduces it.
- **The site opens but login fails**: open `https://<railway address>/health`. If Railway
  answers, the address in `vercel.json` is wrong; if it doesn't, check Railway's deploy logs.
- **Railway crashes on start**: its deploy logs show which variable is missing (the API
  refuses to start in production with development secrets).
- **Uploads over 4.5 MB fail**: requests that pass through Vercel have a body size limit. The
  fix is S3 storage (`ARBA_STORAGE_BACKEND=s3`, `ARBA_S3_BUCKET`, and the AWS keys), where
  the browser uploads directly to the bucket.
