# The API image (ADR-032). Build from the repo root:
#   docker build -f apps/api/Dockerfile -t cornerpin-api .
# Serves uvicorn on $PORT; the same image runs migrations and ops commands as Cloud Run jobs.

FROM ghcr.io/astral-sh/uv:0.9-python3.13-bookworm-slim AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /repo
# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-workspace --package cornerpin-api
COPY alembic.ini ./
COPY apps/api apps/api
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --package cornerpin-api

FROM python:3.13-slim-bookworm
ENV PATH=/repo/.venv/bin:$PATH PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /repo
COPY --from=build /repo /repo
USER nobody
# Cloud Run terminates TLS and sets X-Forwarded-*; trust it for the client address.
CMD ["sh", "-c", "exec uvicorn cornerpin.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
