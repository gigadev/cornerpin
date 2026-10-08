# The decisioning image (ADR-048). Build from the repo root:
#   docker build -f apps/decisioning/Dockerfile -t cornerpin-decisioning .
# Serves uvicorn on $PORT. Holds the ML dependencies so the API image doesn't.

FROM ghcr.io/astral-sh/uv:0.9-python3.13-bookworm-slim AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /repo
# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml uv.lock ./
# uv reads every workspace member's manifest to check the lock; only this service is installed.
COPY apps/api/pyproject.toml apps/api/
COPY apps/decisioning/pyproject.toml apps/decisioning/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-workspace --package cornerpin-decisioning
COPY apps/decisioning apps/decisioning
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --package cornerpin-decisioning

FROM python:3.13-slim-bookworm
# LightGBM's wheel needs the OpenMP runtime.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
ENV PATH=/repo/.venv/bin:$PATH PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /repo
COPY --from=build /repo /repo
USER nobody
CMD ["sh", "-c", "exec uvicorn cornerpin_decisioning.app:app --host 0.0.0.0 --port ${PORT}"]
