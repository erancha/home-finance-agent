# syntax=docker/dockerfile:1
# Build context is the repo root, so both backend/ and frontend/ are reachable.
FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PIP_ROOT_USER_ACTION=ignore PIP_DISABLE_PIP_VERSION_CHECK=1
RUN useradd --system --no-create-home --shell /usr/sbin/nologin hfm
WORKDIR /app
# The pinned lockfile installs first so source edits reuse the dependency layer; it is mounted, not
# copied, so it never lands in the image.
RUN --mount=type=bind,source=backend/requirements.txt,target=/tmp/requirements.txt \
    --mount=type=cache,target=/root/.cache/pip \
    pip install -r /tmp/requirements.txt
COPY backend/pyproject.toml /build/
COPY backend/src /build/src
RUN pip install --no-cache-dir --no-deps /build && rm -rf /build
# The app and alembic resolve config/, alembic.ini and alembic/ against /app, the working directory.
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY config ./config
COPY --from=frontend /frontend/dist ./frontend
ENV HFM_FRONTEND_DIST=/app/frontend
USER hfm
EXPOSE 8010
