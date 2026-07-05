#!/usr/bin/env sh
set -eu

APP_DIR="${APP_DIR:-/opt/royal-regent/royal-regent-nexus}"
REPO_URL="${REPO_URL:-https://github.com/13829313399-a11y/Royal-Regent-Nexus.git}"
BRANCH="${BRANCH:-main}"
CONFIRM_RESET="${CONFIRM_RESET:-}"

if [ "$CONFIRM_RESET" != "DELETE_OLD_ROYAL_REGENT_DEPLOY" ]; then
  echo "This script deletes old containers, Docker volumes, and the app directory." >&2
  echo "Run with CONFIRM_RESET=DELETE_OLD_ROYAL_REGENT_DEPLOY when you are ready." >&2
  exit 1
fi

case "$APP_DIR" in
  /opt/royal-regent/*) ;;
  *)
    if [ "${ALLOW_CUSTOM_APP_DIR:-}" != "1" ]; then
      echo "Refusing to delete custom APP_DIR: $APP_DIR" >&2
      echo "Set ALLOW_CUSTOM_APP_DIR=1 only after confirming this path is safe to remove." >&2
      exit 1
    fi
    ;;
esac

if [ "$APP_DIR" = "/" ] || [ "$APP_DIR" = "/opt" ] || [ "$APP_DIR" = "/opt/royal-regent" ]; then
  echo "Refusing unsafe APP_DIR: $APP_DIR" >&2
  exit 1
fi

if [ -d "$APP_DIR" ]; then
  for compose_file in docker-compose.prod.yml docker-compose.yml docker-compose.yaml compose.yml compose.yaml; do
    if [ -f "$APP_DIR/$compose_file" ]; then
      echo "Stopping Compose stack from $APP_DIR/$compose_file"
      if [ -f "$APP_DIR/.env.production" ]; then
        docker compose -f "$APP_DIR/$compose_file" --env-file "$APP_DIR/.env.production" down --volumes --remove-orphans || true
      else
        docker compose -f "$APP_DIR/$compose_file" down --volumes --remove-orphans || true
      fi
    fi
  done

  echo "Removing old app directory: $APP_DIR"
  rm -rf -- "$APP_DIR"
fi

mkdir -p "$(dirname "$APP_DIR")"
git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"

cd "$APP_DIR"
cp .env.production.example .env.production

docker image prune -f

echo "Clean checkout is ready at $APP_DIR"
echo "Next: edit $APP_DIR/.env.production and replace POSTGRES_PASSWORD/DATABASE_URL."
echo "Then run:"
echo "  cd $APP_DIR"
echo "  docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build"
