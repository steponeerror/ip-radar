# syntax=docker/dockerfile:1

FROM node:22-alpine AS frontend
WORKDIR /build
ARG NPM_REGISTRY=""
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci ${NPM_REGISTRY:+--registry $NPM_REGISTRY}
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 IP_RADAR_DATA_DIR=/app/data
WORKDIR /app
ARG PIP_INDEX_URL=""
# L2 self-update toolchain + F4: docker CLI 不在 Debian 源,加官方源(python:3.12-slim = trixie)
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates curl \
    && install -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian trixie stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt ${PIP_INDEX_URL:+-i $PIP_INDEX_URL}
COPY backend/ ./backend/
# 版本自描述:构建上下文含 .git(.dockerignore 已放行)
COPY .git /app/.git
RUN git describe --tags --always --dirty > /app/BUILD_VERSION 2>/dev/null || echo dev > /app/BUILD_VERSION
COPY --from=frontend /build/dist ./frontend/dist
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
