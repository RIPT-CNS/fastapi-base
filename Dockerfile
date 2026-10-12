# syntax=docker/dockerfile:1
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Same uid as the host user so files created through the bind mount (migrations) stay editable
ARG UID=1000
ARG GID=1000
RUN groupadd --gid "${GID}" app && useradd --uid "${UID}" --gid app --create-home app

WORKDIR /app
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt
COPY --chown=app:app . .

USER app
EXPOSE 8000
# ENVIRONMENT=dev -> hot reload, otherwise WEB_CONCURRENCY worker processes
CMD ["python", "-m", "app.cli", "serve"]
