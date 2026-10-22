# Deploying Arba on Vercel

Everything runs in one Vercel project:

| Part | On Vercel |
|---|---|
| Web app | static files built from `apps/web` |
| API (FastAPI) | one Python function, `api/index.py`, serving every `/api/...` path |
| Database | Postgres from the Vercel Marketplace (Neon) |
| Uploaded files | a table in that database (`stored_files`) |
| Periodic work | Vercel Cron calls `/api/v1/cron/tick` (morning summaries, reminders, letters) |

The API sets itself up: on the first request after a deploy it migrates the database and
loads the reference data (only when those files changed). Urgent notifications are sent as
soon as they are created.

## Once: set up the project

1. **Settings → Build and Deployment**
   - Root Directory: empty (the repository root).
   - Framework Preset: **Other**, every override **off**; `vercel.json` decides.
2. **Storage → Create Database → Neon (Postgres)** → connect it to this project, all
   environments. This adds `DATABASE_URL` and `DATABASE_URL_UNPOOLED`; Arba reads them.
3. **Settings → Environment Variables** (Production):

   | Variable | Value |
   |---|---|
   | `ARBA_ENV` | `production` |
   | `ARBA_JWT_SECRET` | a long random string: run `openssl rand -hex 32` |
   | `ARBA_INBOUND_WEBHOOK_PASSWORD` | another `openssl rand -hex 32` |
   | `CRON_SECRET` | another `openssl rand -hex 32` (Vercel sends it with cron calls) |
   | `ARBA_SMTP_HOST` | `smtp.gmail.com` |
   | `ARBA_SMTP_PORT` | `587` |
   | `ARBA_SMTP_STARTTLS` | `true` |
   | `ARBA_SMTP_USER` | your Gmail address |
   | `ARBA_SMTP_PASSWORD` | a **new** Gmail app password |
   | `ARBA_EMAIL_FROM` | `Arba <your Gmail address>` |
   | `ARBA_EMAIL_ALLOWED_RECIPIENTS` | `["your Gmail address"]` while testing: mail meant for anyone else (including letters to authorities) comes to you, marked as a test |
   | `ANTHROPIC_API_KEY` | optional: Claude reads permits and writes letters far better than the fallback rules |

   Set automatically on Vercel, no need to add: the site address (`ARBA_APP_URL` from the
   production domain), file storage in the database, secure cookies, no worker process.
4. **Deployments → Redeploy** (or push to `main`).
5. Open `https://<your-site>/api/health` → `{"status":"ok"}`. The first `/api/v1/...`
   request takes a few seconds while the database is set up. Then register in the app.

## Limits on Vercel

- **Uploads up to 4.5 MB per file.** Vercel limits request bodies sent to functions. Larger
  files need direct-to-storage uploads (Vercel Blob or S3): `ARBA_STORAGE_BACKEND=s3` with
  `ARBA_S3_BUCKET` and AWS keys works today.
- **Cron on the Hobby plan runs once a day** (05:00 UTC, morning in Israel). Urgent
  notifications don't wait for it; reminders and new letters to authorities are prepared then.
  On Pro, change the schedule in `vercel.json` (e.g. `*/10 * * * *`).
- WhatsApp stays off until Meta is set up ([whatsapp-setup.md](whatsapp-setup.md)); then set
  `ARBA_WHATSAPP_PROVIDER=cloud` and its variables.

## When something doesn't work

- **"500 FUNCTION_INVOCATION_FAILED"**: Vercel → the deployment → **Logs**, filter by
  `/api`. The usual causes: the database isn't connected (step 2), or `ARBA_ENV=production`
  without `ARBA_JWT_SECRET` / `ARBA_INBOUND_WEBHOOK_PASSWORD` (the API refuses to start with
  development secrets).
- **Build fails**: the build log; locally `npm ci && npm run build` reproduces it.
- **Running the API elsewhere** (any Docker host): `backend/Dockerfile` migrates, seeds and
  serves on `$PORT`.
