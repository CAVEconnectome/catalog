# CLAUDE.md

## Running the tests locally

The suite is self-contained: it needs no Docker, no Postgres and no other CAVE service.
`tests/conftest.py` sets `AUTH_ENABLED=false` and gives each test its own temporary SQLite
database, with the tables made by `create_all`; the calls out to middle_auth,
MaterializationEngine and Cloud Storage are mocked.

```bash
uv run pytest -q -p no:cacheprovider
```

Expected: everything passes (322 tests as of v0.1.3). `just test` is the same command;
`just` is optional, and the justfile shows what each recipe runs.

Before a PR, also run the type check and the linter (`just checks` runs all three):

```bash
uv run mypy src/
uv run ruff format src/ tests/ && uv run ruff check src/ tests/ --fix
```

- **SQLite isn't Postgres.** The tests build the schema from the SQLAlchemy models
  (`create_all`), not from the Alembic migrations, so they won't catch a migration that has
  drifted from `db/models.py` (for example a partial unique index or a NOT NULL that exists
  in one and not the other). After changing a model or a migration, run the migrations
  against a real Postgres too:

  ```bash
  docker compose up postgres -d
  DATABASE_URL=postgresql+asyncpg://cave_catalog:cave_catalog@localhost:5432/cave_catalog \
    uv run alembic upgrade head
  ```

- **Running the service** (to try it from a client): `just dev` starts Postgres in Docker and
  uvicorn on the host at `http://localhost:8000/catalog/docs`, with auth off. Apply the
  migrations first, as above. With `MAT_ENGINE_URL` unset, registration skips the
  MaterializationEngine checks (name reservation and table verification).
- **Port 5432:** compose's Postgres publishes 5432, so stop any other Postgres container on
  that port first (MaterializationEngine's `mat-test-pg` uses it too).

## Releasing a new version

Every new version needs two things, and they must stay in sync:

1. **A `v{version}` git tag pushed to this repo.** Cloud Build triggers on the tag
   (`cloudbuild.yaml`) and pushes the image `caveconnectome/cave-catalog:v{version}`.
2. **`charts/catalog/Chart.yaml` in `CAVEconnectome/cave-helm-charts` updated** so that
   `appVersion` is the new version and the chart `version` is the same number. The chart
   deploys the image tag `v{appVersion}`, so a chart that isn't updated keeps deploying the
   old image.

The app and the chart share one version number. The chart can also be bumped on its own
(for a template change), so the new version must be past both: bump from whichever of the
app version (`pyproject.toml`) and the chart `version` is higher. For example, app `0.1.0`
and chart `0.1.3` give a patch release of `0.1.4`, and the app skips `0.1.1`–`0.1.3`.

### How to do it

Run the **publish release** GitHub Actions workflow (`.github/workflows/release.yml`) and
pick `major`, `minor` or `patch`. It does all of the above: picks the higher base version,
bumps `pyproject.toml` with `bump-my-version` (which also relocks `uv.lock` in the same
commit), pushes the commit and tag, creates the GitHub Release, and commits the new
`version` and `appVersion` to `cave-helm-charts`. Use `dry-run` to check the version first.

Don't bump the version, tag, or edit `Chart.yaml` by hand. Doing only part of it leaves the
tag, image and chart out of sync.
