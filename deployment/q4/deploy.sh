#!/usr/bin/env sh
set -eu
cd "$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
command -v docker >/dev/null 2>&1 || { echo 'Docker is required. Install it for the server OS first.' >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo 'Docker Compose v2 is required.' >&2; exit 1; }
test -f site/summary/index.html || { echo 'Missing site files; extract the complete package.' >&2; exit 1; }
test -f .env || cp .env.example .env
docker compose config --quiet
docker compose pull
docker compose run --rm --no-deps dashboard caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker compose up -d --wait --wait-timeout 90
docker compose ps
echo 'Service is healthy. Verify the public URL using: python3 check.py https://YOUR_DOMAIN'
