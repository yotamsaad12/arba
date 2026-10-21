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
