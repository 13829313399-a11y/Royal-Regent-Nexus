#!/usr/bin/env sh
set -eu

ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
PUBLIC_ORIGIN="${AI_PUBLIC_ORIGIN:-}"
EXPECT_DISABLED_MARKER="${AI_PILOT_EXPECT_DISABLED_MARKER:-true}"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

compose() {
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
}

read_env_value() {
  key="$1"
  awk -v wanted="$key" '
    {
      line = $0
      sub(/^[[:space:]]*export[[:space:]]+/, "", line)
      equals = index(line, "=")
      if (equals == 0) next
      candidate = substr(line, 1, equals - 1)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", candidate)
      if (candidate == wanted) value = substr(line, equals + 1)
    }
    END { print value }
  ' "$ENV_FILE" | tr -d '\r'
}

require_env_exact() {
  key="$1"
  expected="$2"
  actual="$(read_env_value "$key")"
  [ "$actual" = "$expected" ] || fail "$key is not set to the required safe value"
}

require_env_nonempty() {
  key="$1"
  actual="$(read_env_value "$key")"
  [ -n "$actual" ] || fail "$key is missing"
}

require_env_integer_range() {
  key="$1"
  minimum="$2"
  maximum="$3"
  actual="$(read_env_value "$key")"
  case "$actual" in
    ""|*[!0-9]*) fail "$key must be an integer" ;;
  esac
  [ "$actual" -ge "$minimum" ] && [ "$actual" -le "$maximum" ] \
    || fail "$key is outside the approved Pilot range"
}

require_hsts_header() {
  header_path="$1"
  route_label="$2"
  hsts_value="$(
    tr '[:upper:]' '[:lower:]' < "$header_path" \
      | awk -F ':' '/^strict-transport-security:/ { sub(/^[^:]*:[[:space:]]*/, ""); sub(/\r$/, ""); print; exit }'
  )"
  [ -n "$hsts_value" ] || fail "Strict-Transport-Security is missing on $route_label"
  hsts_max_age="$(printf '%s\n' "$hsts_value" | sed -n 's/.*max-age=\([0-9][0-9]*\).*/\1/p')"
  case "$hsts_max_age" in
    ""|*[!0-9]*) fail "Strict-Transport-Security max-age is invalid on $route_label" ;;
  esac
  [ "$hsts_max_age" -ge 31536000 ] \
    || fail "Strict-Transport-Security max-age must be at least 31536000 on $route_label"
}

[ -f "$ENV_FILE" ] || fail "Environment file not found: $ENV_FILE"
[ -f "$COMPOSE_FILE" ] || fail "Compose file not found: $COMPOSE_FILE"
case "$PUBLIC_ORIGIN" in
  https://*) ;;
  *) fail "AI_PUBLIC_ORIGIN must be an HTTPS origin" ;;
esac
case "${PUBLIC_ORIGIN#https://}" in
  ""|*/*|*:* ) fail "AI_PUBLIC_ORIGIN must contain only an HTTPS hostname" ;;
esac
PUBLIC_ORIGIN="${PUBLIC_ORIGIN%/}"

# Read only non-secret rollout controls. Values are validated but never printed.
require_env_exact APP_ENV production
require_env_exact SESSION_COOKIE_SECURE true
require_env_exact AI_ENABLED true
require_env_exact AI_PILOT_ENABLED true
require_env_exact AI_PILOT_PUBLIC_TLS_VERIFIED true
require_env_exact AI_RUNTIME_DISABLE_PATH /app/backend/control/ai.disabled
require_env_exact AI_LOG_RAW_PROMPTS false
require_env_exact AI_LOG_RAW_TOOL_RESULTS false
require_env_exact AI_PROVIDER qwen
require_env_exact AI_REGION cn-beijing
require_env_exact AI_DEFAULT_MODEL qwen3.7-plus
require_env_exact AI_BASE_URL ""
require_env_nonempty AI_PILOT_USER_IDS
require_env_nonempty AI_PILOT_FACTORY_IDS
require_env_nonempty AI_WORKSPACE_ID
require_env_nonempty DASHSCOPE_API_KEY
require_env_integer_range AI_PILOT_MAX_CONCURRENT_PER_USER 1 2
require_env_integer_range AI_PILOT_REQUESTS_PER_MINUTE 1 60
require_env_integer_range AI_PILOT_DAILY_TOKEN_BUDGET 1 100000000
require_env_integer_range AI_PILOT_MAX_OUTPUT_TOKENS 1 16384
require_env_integer_range AI_MAX_TOOL_ROUNDS 0 6
require_env_integer_range AI_MAX_TOOL_RESULT_ROWS 1 50
require_env_integer_range AI_MAX_TOOL_RESULT_BYTES 1 65536
require_env_integer_range AI_MAX_INPUT_MESSAGE_CHARS 1 8000
require_env_integer_range AI_MAX_INPUT_CHARS 1 40000
require_env_integer_range AI_MAX_IMAGE_TOTAL_BYTES 1 12582912

vision_enabled="$(read_env_value AI_CLOUD_VISION_ENABLED)"
case "$vision_enabled" in
  true)
    require_env_exact AI_VISION_MODEL qwen3.7-plus
    ;;
  false) ;;
  *) fail "AI_CLOUD_VISION_ENABLED must be true or false" ;;
esac

tool_rounds="$(read_env_value AI_MAX_TOOL_ROUNDS)"
max_tool_result_bytes="$(read_env_value AI_MAX_TOOL_RESULT_BYTES)"
max_input_message_chars="$(read_env_value AI_MAX_INPUT_MESSAGE_CHARS)"
max_input_chars="$(read_env_value AI_MAX_INPUT_CHARS)"
max_image_total_bytes="$(read_env_value AI_MAX_IMAGE_TOTAL_BYTES)"
max_output_tokens="$(read_env_value AI_PILOT_MAX_OUTPUT_TOKENS)"
daily_budget="$(read_env_value AI_PILOT_DAILY_TOKEN_BUDGET)"
provider_calls=$((tool_rounds + 1))
replay_factor=$((tool_rounds * (tool_rounds + 1) / 2))
system_context_reservation=16384
tool_schema_reservation=65536
text_reservation=$((
  provider_calls * (
    max_input_chars
    + max_input_message_chars
    + system_context_reservation
    + tool_schema_reservation
  )
  + replay_factor * 8 * max_tool_result_bytes
  + replay_factor * max_output_tokens
  + provider_calls * max_output_tokens
))
required_reservation="$text_reservation"
if [ "$vision_enabled" = "true" ]; then
  vision_reservation=$((
    max_input_chars
    + max_image_total_bytes
    + max_output_tokens
    + system_context_reservation
  ))
  if [ "$vision_reservation" -gt "$required_reservation" ]; then
    required_reservation="$vision_reservation"
  fi
fi
[ "$daily_budget" -ge "$required_reservation" ] \
  || fail "AI_PILOT_DAILY_TOKEN_BUDGET is below the conservative request reservation"

api_id="$(compose ps -q api)"
[ -n "$api_id" ] || fail "API container is not running"
control_mount_writable="$(
  docker inspect --format '{{range .Mounts}}{{if eq .Destination "/app/backend/control"}}{{.RW}}{{end}}{{end}}' "$api_id"
)"
[ "$control_mount_writable" = "false" ] \
  || fail "AI runtime control volume is missing or writable by the API container"
compose exec -T api test -d /app/backend/control \
  || fail "AI runtime control directory is unavailable"
case "$EXPECT_DISABLED_MARKER" in
  true)
    compose exec -T api test -f /app/backend/control/ai.disabled \
      || fail "AI runtime disable marker must remain active during preflight"
    ;;
  false)
    compose exec -T api test ! -e /app/backend/control/ai.disabled \
      || fail "AI runtime disable marker is active"
    ;;
  *) fail "AI_PILOT_EXPECT_DISABLED_MARKER must be true or false" ;;
esac

https_headers="$(mktemp)"
home_headers="$(mktemp)"
ai_headers="$(mktemp)"
health_body="$(mktemp)"
http_headers="$(mktemp)"
trap 'rm -f "$https_headers" "$home_headers" "$ai_headers" "$health_body" "$http_headers"' EXIT INT TERM

curl --proto '=https' --tlsv1.2 --fail --silent --show-error \
  --connect-timeout 5 --max-time 15 \
  --dump-header "$https_headers" \
  --output "$health_body" \
  "$PUBLIC_ORIGIN/health"
grep -q '"status"[[:space:]]*:[[:space:]]*"ok"' "$health_body" \
  || fail "Public HTTPS health response is not healthy"
require_hsts_header "$https_headers" "/health"

curl --proto '=https' --tlsv1.2 --fail --silent --show-error \
  --connect-timeout 5 --max-time 15 \
  --dump-header "$home_headers" --output /dev/null \
  "$PUBLIC_ORIGIN/"
require_hsts_header "$home_headers" "/"

anonymous_status="$(
  curl --proto '=https' --tlsv1.2 --silent --show-error \
    --connect-timeout 5 --max-time 15 \
    --dump-header "$ai_headers" \
    --output /dev/null --write-out '%{http_code}' \
    "$PUBLIC_ORIGIN/api/ai/capabilities"
)"
[ "$anonymous_status" = "401" ] \
  || fail "Anonymous AI capabilities request must return 401"
require_hsts_header "$ai_headers" "/api/ai/capabilities"

http_origin="http://${PUBLIC_ORIGIN#https://}"
http_status="$(
  curl --silent --show-error --connect-timeout 5 --max-time 15 \
    --dump-header "$http_headers" --output /dev/null --write-out '%{http_code}' \
    "$http_origin/"
)"
case "$http_status" in
  301|308) ;;
  *) fail "Public HTTP must redirect permanently to HTTPS" ;;
esac
redirect_location="$(
  tr '[:upper:]' '[:lower:]' < "$http_headers" \
    | awk -F ':' '/^location:/ { sub(/^[^:]*:[[:space:]]*/, ""); sub(/\r$/, ""); print; exit }'
)"
expected_origin="$(printf '%s\n' "$PUBLIC_ORIGIN" | tr '[:upper:]' '[:lower:]')"
case "$redirect_location" in
  "$expected_origin"|"$expected_origin/"|"$expected_origin"/*) ;;
  *) fail "HTTP redirect target does not match AI_PUBLIC_ORIGIN" ;;
esac

echo "AI Pilot readiness checks passed: TLS/HSTS, anonymous auth boundary, and safe rollout controls."
