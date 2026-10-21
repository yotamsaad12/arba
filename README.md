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
make seed      # loads the private-house template
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
infra/                 docker-compose for local services
```

## Changing things

- **API changed?** Run `make api-client` so the web app sees the new types.
- **Model changed?** `cd backend && .venv/bin/alembic revision --autogenerate -m "..."`, then `make migrate`.
- **Template changed?** Bump `version` in the YAML and run `make seed`. Existing projects keep the version they were created from.
