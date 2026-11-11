ARG BASE_IMAGE=python:3.12-slim

# pyproject.toml and uv.lock both record the project's own version, which every release
# bumps. This stage blanks it out, so the dependency stage below sees byte-identical files
# from one release to the next and stays cached until a dependency actually changes.
FROM ${BASE_IMAGE} AS lockfiles
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN sed -i -E 's/^(current_)?version = .*/\1version = "0.0.0"/' pyproject.toml \
  && sed -i '/^name = "cave-catalog"$/{n;s/^version = .*/version = "0.0.0"/}' uv.lock

# Build stage: the locked dependencies, without the project itself, in /app/.venv.
# uv is mounted for the RUN only, so it stays out of the image.
FROM ${BASE_IMAGE} AS deps
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0
WORKDIR /app
COPY --from=lockfiles /app/pyproject.toml /app/uv.lock ./
RUN --mount=from=ghcr.io/astral-sh/uv:0.9,source=/uv,target=/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
  uv sync --frozen --no-install-project --no-dev

FROM ${BASE_IMAGE}
ENV UV_PYTHON_DOWNLOADS=0 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
WORKDIR /app
# The dependency layer keeps its digest across releases that only change application
# code, so a push uploads just the layers below it.
COPY --from=deps /app/.venv /app/.venv
COPY alembic.ini ./
COPY migrations ./migrations
COPY --chmod=755 entrypoint.sh ./
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
# Installs only the project (editable, pointing at /app/src): every dependency is already
# in the venv. This gives the app the package metadata it reads its version from.
RUN --mount=from=ghcr.io/astral-sh/uv:0.9,source=/uv,target=/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
  uv sync --frozen --no-dev

EXPOSE 80

CMD ["./entrypoint.sh"]
