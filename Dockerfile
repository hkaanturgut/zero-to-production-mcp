# One image, two entrypoints (server and dms), so the pipeline builds and
# scans exactly one artifact. Multi-stage: build tools never ship.
# In an enterprise, point this at a base image mirrored into your own ACR.
ARG PYTHON_IMAGE=python:3.11-slim
FROM ${PYTHON_IMAGE} AS build
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --extra otel
COPY src ./src
RUN uv sync --frozen --no-dev --extra otel

FROM ${PYTHON_IMAGE}
RUN useradd --uid 10001 --create-home app
WORKDIR /app
COPY --from=build --chown=app:app /app /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8080
USER 10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/healthz')"
# APP_ENTRY picks the entry point of this one image:
#   live-server  the file built on stage (src/live/server.py)
#   server       the full reference build (src/server)
#   dms          the mock dealer system
ENV APP_ENTRY=server
CMD ["sh", "-c", "exec \"$APP_ENTRY\""]
