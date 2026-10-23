# ארבע (Arba)

From building permit to Form 4: a system that knows what to do next, what is blocked, and who has to approve it.

- Product spec: [SPEC.md](SPEC.md)
- Technical spec: [TECH_SPEC.md](TECH_SPEC.md)

## Running locally

Requirements: Docker, Python 3.12+, Node 22+.

```sh
make setup     # backend venv + npm workspaces
make up        # Postgres, Redis, Mailpit
make migrate
make seed      # loads the private-house template, localities, committees and contacts
make api       # terminal 1: http://localhost:8000/docs
make web       # terminal 2: http://localhost:5180
```

`make test` runs the backend tests against the `arba_test` database (created by Docker on first start).
`make typecheck` lints the backend and typechecks the frontend.

### Trying the inbox locally

Every project has an inbox address (shown on the project page). Without a mail provider, send a
sample email from an approving authority straight to the local webhook:

```sh
make test-email TO=p-xxxxxxxx@in.arba.co.il                       # water company approval + PDF
make test-email TO=p-xxxxxxxx@in.arba.co.il ARGS="--sample hfc"   # Home Front Command request
make test-email TO=p-xxxxxxxx@in.arba.co.il ARGS="--reply --attach plan.pdf"
```

Uploaded and received files are stored under `backend/.storage/` in development.

### Filing suggestions (AI)

Every incoming email and every unfiled upload gets a suggestion: which requirement it belongs
to and what status to set. People approve it with one click or pick something else.

- With `ANTHROPIC_API_KEY` set, suggestions come from Claude (`ARBA_AI_MODEL`, default
  `claude-opus-5-5`, effort `ARBA_AI_EFFORT=low`). It reads attached PDFs and images.
- Without a key, a built-in rules engine suggests from the sender, subject and file names.
- `ARBA_AI_PROVIDER=rules|claude|auto` forces one or the other.

### Notifications and WhatsApp

Arba pushes what people need to do: urgent items right away (outside each person's quiet hours,
including Shabbat), everything else in one morning summary. Channels: in-app bell, email
(Mailpit at http://localhost:8025 in dev) and WhatsApp, where approval requests come with
"approve" / "change" buttons.

- In dev, WhatsApp runs against a simulator: connect a number in Settings, then open
  http://localhost:5180/dev/whatsapp to see the messages and press the buttons.
- The notification worker runs inside the API in dev. In production run `python -m app.worker`
  and set `ARBA_RUN_WORKER_IN_API=false`.
- Going live with real WhatsApp: [docs/whatsapp-setup.md](docs/whatsapp-setup.md).

### Permits and the directory of approving bodies

A project starts from its building permit. The person uploads the permit PDF, Arba reads it
(Claude, or text rules without an API key) and they confirm the fields. Arba then checks the
file, number, validity, and that the committee on the permit is the one responsible for the
chosen locality. The project opens either way, as "waiting for permit verification" until the
checks pass; the last step is the person finding the permit on the committee's own site.

- Localities, municipalities and planning committees come from official open data
  (data.gov.il and the Planning Administration map), snapshotted in
  `backend/app/modules/directory/data/reference.json`. Refresh with
  `cd backend && .venv/bin/python -m app.scripts.sync_reference_data`, then `make seed`.
- Contacts of approving bodies are in `backend/app/modules/directory/data/contacts.yaml`:
  only what the body publishes itself, each with its source page and date. Arba also learns
  contacts from mail filed to a requirement (shown as "learned from mail").

### A complete checklist

- **Permit conditions.** After the permit file is checked, Arba reads the conditions written in
  it (Claude, or numbered-line rules) and proposes for each one a new step or the existing step
  it belongs to. The person approves; new steps hold up the Form 4 submission.
- **The authority's own list.** `backend/app/modules/directory/data/form4_lists.yaml` holds
  what each local authority adds to the base template, from its published sources. Projects
  get it at creation; `make seed` applies updates to open projects.
- **Learning from authorities.** When an approved filing is a request for information or a
  rejection, what the authority asked for joins the step's documents and is recorded in
  `checklist_feedback` for improving the base template.

### Writing to the authorities

Arba drafts requests to the approving bodies (committee, water corporation, fire and rescue,
Home Front Command) once the permit checks out, and reminders after 7 days without an answer;
after 3 reminders it suggests calling. Nothing is sent without the person's approval (in the
app or with the WhatsApp button). Mail goes out from Arba with the project inbox as Reply-To,
so answers land in the project's conversation, and the person is copied. Bodies that take
requests only on their website get the text ready to paste. With
`ARBA_EMAIL_ALLOWED_RECIPIENTS` set (dev with a real mail server), letters go to the first
allowed address instead of the authority, marked as a test.

### Professionals and document checks

- **Requests to professionals.** From a step, the person asks the surveyor, engineer, lab or
  contractor for documents. They get an email and/or WhatsApp with a personal link
  (`/r/<token>`): a mobile page that shows what is asked, for which project and step, and takes
  uploads with no account. Files go straight into the step; the person is told; open requests
  are sent again every 3 days (up to 3 reminders). The team is kept per project.
- **Document checks.** Every document filed under a step is checked: the right kind for the
  step, signed and stamped, about this property (address, gush/helka, permit number), still
  valid. Claude reads the document; without an API key, text rules check the identifiers and
  expiry dates in PDFs. Problems are shown on the step and notified; when all the documents a
  step needs are in and check out, Arba proposes marking it done (one tap, also on WhatsApp).

### Projects already under way

When a project started before Arba, the person says which stage it is at; Arba marks the
required steps before it as done, then gathers what already exists:

- **Mailbox scan** (`/projects/:id/import`): one-time, read-only access. Arba searches only
  for mail about the project (permit and request numbers, block, street address, and building
  mail from the area's approving bodies), imports it into the project inbox and suggests a
  filing per conversation. One notification when the scan ends, not one per email. Gmail
  access is online-only (no refresh token) and revoked when the scan finishes.
- **Bulk upload**: any number of files, each filed by the usual suggestions.
- **Gap report**: what was found per requirement, and steps already done with no documents.

In dev the scan runs against a simulated mailbox. For Gmail set `ARBA_GOOGLE_CLIENT_ID` and
`ARBA_GOOGLE_CLIENT_SECRET` (a Google Cloud OAuth web client with the Gmail API enabled and
`<app_url>/api/v1/mailbox/google/callback` as redirect URI). `gmail.readonly` is a restricted
scope: up to 100 test users before Google's verification and security assessment.

## Deploying

Everything (web app, API, database, files, cron) on Vercel: [docs/deploy.md](docs/deploy.md).

## Layout

```
apps/web/              React + Vite web app (Hebrew, RTL, mobile-first)
  src/world/           3D construction site (three.js / React Three Fiber), lazy-loaded
  src/scene/           SVG version of the site, and the progress → scene model
packages/api-client/   TypeScript client generated from the API's OpenAPI schema
packages/shared/       Statuses and rules shared by web and (later) mobile
packages/i18n/         Hebrew strings
backend/               FastAPI, SQLAlchemy, Alembic
  app/modules/requirements/engine.py      dependency engine and critical path
  app/modules/templates/data/*.yaml       checklist templates
  app/modules/directory/data/             localities, committees and contacts of approving bodies
  app/modules/permits/                    reading and checking the building permit
  app/modules/catchup/                    projects already under way: mailbox scan, gap report
  app/modules/team/                       the project team and upload links for professionals
  app/modules/checks/                     checking documents filed under a step
infra/                 docker-compose for local services
```

## Changing things

- **API changed?** Run `make api-client` so the web app sees the new types.
- **Model changed?** `cd backend && .venv/bin/alembic revision --autogenerate -m "..."`, then `make migrate`.
- **Template changed?** Bump `version` in the YAML and run `make seed`. Existing projects keep the version they were created from.
