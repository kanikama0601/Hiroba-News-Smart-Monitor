# Install uv
FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Change the working directory to the `app` directory
WORKDIR /app
ENV UV_LINK_MODE=copy
ENV UV_PYTHON_DOWNLOADS=0

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-editable

COPY . .

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable

RUN rm /app/.venv/bin/python && ln -s "/usr/bin/python3.13" /app/.venv/bin/python

# 実行用イメージ
FROM gcr.io/distroless/python3-debian13 AS runner
WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH"
ENV TZ="Asia/Tokyo"

COPY --from=builder /app /app
ENTRYPOINT ["python", "src/app.py"]
