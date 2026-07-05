#!/usr/bin/env sh
set -eu

APP_DIR="${APP_DIR:-/opt/royal-regent/royal-regent-nexus}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-.env.production}"

cd "$APP_DIR"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $APP_DIR/$ENV_FILE. Copy .env.production.example to $ENV_FILE and edit it first." >&2
  exit 1
fi

if grep -q "change-this-long-random-password" "$ENV_FILE"; then
  echo "$APP_DIR/$ENV_FILE still contains the example database password. Replace it before starting production." >&2
  exit 1
fi

git fetch --prune
git pull --ff-only

docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --build
docker compose -f "$COMPOSE_FILE" ps
docker image prune -f
