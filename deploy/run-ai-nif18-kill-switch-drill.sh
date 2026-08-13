#!/usr/bin/env sh
set -eu
export LC_ALL=C

CONFIRMATION="${CONFIRM_NIF18_KILL_SWITCH_DRILL:-}"
PUBLIC_ORIGIN="${AI_PUBLIC_ORIGIN:-}"
COOKIE_FILE="${AI_DRILL_COOKIE_FILE:-}"
ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

compose() {
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
}

[ "$CONFIRMATION" = "DISABLE_AI_AND_VERIFY_BUSINESS" ] \
  || fail "explicit kill-switch drill confirmation is required"
case "$PUBLIC_ORIGIN" in
  https://*) ;;
  *) fail "AI_PUBLIC_ORIGIN must be an HTTPS origin" ;;
esac
[ -f "$COOKIE_FILE" ] || fail "AI_DRILL_COOKIE_FILE is required"
[ -f "$ENV_FILE" ] || fail "production environment file is unavailable"
[ -f "$COMPOSE_FILE" ] || fail "production Compose file is unavailable"

api_id="$(compose ps -q api)"
worker_id="$(compose ps -q ai-task-worker)"
[ -n "$api_id" ] || fail "API container is not running"
[ -n "$worker_id" ] || fail "AI Task Worker container is not running"

api_volume="$(
  docker inspect --format '{{range .Mounts}}{{if eq .Destination "/app/backend/control"}}{{.Name}}{{end}}{{end}}' "$api_id"
)"
worker_volume="$(
  docker inspect --format '{{range .Mounts}}{{if eq .Destination "/app/backend/control"}}{{.Name}}{{end}}{{end}}' "$worker_id"
)"
[ -n "$api_volume" ] && [ "$api_volume" = "$worker_volume" ] \
  || fail "API and Worker do not share the runtime control volume"

before_health="$(mktemp)"
after_health="$(mktemp)"
ai_body="$(mktemp)"
trap 'rm -f "$before_health" "$after_health" "$ai_body"' EXIT INT TERM

curl --proto '=https' --tlsv1.2 --fail --silent --show-error \
  --connect-timeout 5 --max-time 15 \
  "$PUBLIC_ORIGIN/health" > "$before_health"
grep -q '"status"[[:space:]]*:[[:space:]]*"ok"' "$before_health" \
  || fail "ordinary health was not green before the drill"

# The helper has no network and writes only the shared control marker. The
# marker intentionally remains present after this script, including on success.
docker run --rm --network none -v "$api_volume:/control" postgres:16-alpine \
  sh -c 'umask 077; : > /control/ai.disabled'

curl --proto '=https' --tlsv1.2 --fail --silent --show-error \
  --connect-timeout 5 --max-time 20 \
  --cookie "$COOKIE_FILE" \
  --header 'Content-Type: application/json' \
  --data '{"messages":[{"role":"user","content":[{"type":"input_text","text":"NIF-18 kill-switch drill"}]}],"page_context":null}' \
  "$PUBLIC_ORIGIN/api/ai/responses" > "$ai_body"
grep -q '"code"[[:space:]]*:[[:space:]]*"AI_DISABLED"' "$ai_body" \
  || fail "authenticated AI request was not rejected by the kill switch"

curl --proto '=https' --tlsv1.2 --fail --silent --show-error \
  --connect-timeout 5 --max-time 15 \
  "$PUBLIC_ORIGIN/health" > "$after_health"
grep -q '"status"[[:space:]]*:[[:space:]]*"ok"' "$after_health" \
  || fail "ordinary health was not green after the AI kill switch"
curl --proto '=https' --tlsv1.2 --fail --silent --show-error \
  --connect-timeout 5 --max-time 15 \
  --output /dev/null "$PUBLIC_ORIGIN/"

echo "NIF-18 kill-switch drill passed; AI remains disabled by /app/backend/control/ai.disabled."
