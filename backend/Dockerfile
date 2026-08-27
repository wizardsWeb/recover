# ============================================================================
# Recover backend — production image.
#
# Two stages so the runtime layer carries a resolved virtualenv and the app,
# and nothing else: no Poetry, no compiler, no build cache. The venv is built
# in-project in the builder precisely so it can be copied as one directory.
#
# Both stages use WORKDIR /app deliberately. A virtualenv is not relocatable:
# every console script in .venv/bin carries a shebang with the interpreter's
# absolute build-time path, so a venv built at /build and copied to /app dies
# with `exec .../uvicorn: no such file or directory` — the script is present,
# its shebang's interpreter is not. Building where it will run avoids that.
# ============================================================================

# ---------- builder ----------
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VERSION=1.8.3

RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"

WORKDIR /app

# Manifests only, so this layer survives every source-only change. README.md is
# here because pyproject declares it — Poetry reads the metadata even under
# --no-root, and a missing readme fails the parse.
COPY pyproject.toml poetry.lock README.md ./

# --only main drops pytest/ruff/mypy; --no-root skips installing the app itself,
# which is copied as source rather than built as a wheel.
RUN poetry config virtualenvs.in-project true \
 && poetry install --only main --no-root --no-interaction --no-ansi

# ---------- runtime ----------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    PORT=8000 \
    HOST=0.0.0.0

# A system account with no login shell of its own claim on /app. Container Apps
# does not require a non-root user, but an image that never needs root is one
# less thing an RCE could stand on.
RUN groupadd --system app \
 && useradd --system --gid app --home /app --shell /bin/bash app

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app app ./app

USER app

EXPOSE 8000

# python rather than curl: the slim image ships no curl, and adding one just to
# probe a local port costs more than it buys.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()" || exit 1

# uvloop and httptools are named explicitly rather than left to uvicorn's
# autodetection, so a missing wheel fails loudly instead of silently falling
# back to asyncio and h11.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--loop", "uvloop", "--http", "httptools"]
