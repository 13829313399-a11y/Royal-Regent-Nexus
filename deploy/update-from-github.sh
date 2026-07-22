#!/usr/bin/env sh
set -eu

APP_DIR="${APP_DIR:-/opt/royal-regent/royal-regent-nexus}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-.env.production}"
UPSTREAM="${UPSTREAM:-origin/main}"
BACKUP_ROOT="${BACKUP_ROOT:-/opt/royal-regent/backups}"
HEALTH_TIMEOUT_SECONDS="${HEALTH_TIMEOUT_SECONDS:-120}"

compose() {
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

container_health() {
  docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$1"
}

wait_for_healthy() {
  container_id="$1"
  service_label="$2"
  waited=0

  while [ "$waited" -lt "$HEALTH_TIMEOUT_SECONDS" ]; do
    health="$(container_health "$container_id" 2>/dev/null || true)"
    if [ "$health" = "healthy" ] || [ "$health" = "running" ]; then
      echo "$service_label is $health"
      return 0
    fi
    if [ "$health" = "unhealthy" ] || [ "$health" = "exited" ] || [ "$health" = "dead" ]; then
      docker logs --tail 120 "$container_id" >&2 || true
      fail "$service_label became $health"
    fi
    sleep 2
    waited=$((waited + 2))
  done

  docker logs --tail 120 "$container_id" >&2 || true
  fail "$service_label did not become healthy within ${HEALTH_TIMEOUT_SECONDS}s"
}

capture_database_state() {
  compose exec -T db sh -lc 'psql --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --tuples-only --no-align --field-separator="|" --set ON_ERROR_STOP=1 --command "
    SELECT '\''alembic_version'\'', version_num FROM alembic_version
    UNION ALL SELECT '\''auth_users'\'', count(*)::text FROM auth_users
    UNION ALL SELECT '\''auth_sessions'\'', count(*)::text FROM auth_sessions
    UNION ALL SELECT '\''auth_roles'\'', count(*)::text FROM auth_roles
    UNION ALL SELECT '\''auth_user_roles'\'', count(*)::text FROM auth_user_roles
    UNION ALL SELECT '\''molding_sample_orders'\'', count(*)::text FROM molding_sample_orders
    UNION ALL SELECT '\''molding_sample_items'\'', count(*)::text FROM molding_sample_items
    UNION ALL SELECT '\''molding_notifications'\'', count(*)::text FROM molding_sample_notifications
    UNION ALL SELECT '\''molding_notifications_unread'\'', count(*)::text FROM molding_sample_notifications WHERE status = '\''未读'\''
    UNION ALL SELECT '\''system_notifications'\'', count(*)::text FROM system_notifications
    UNION ALL SELECT '\''system_notifications_unread'\'', count(*)::text FROM system_notifications WHERE status = '\''unread'\''
    UNION ALL SELECT '\''internal_quotes'\'', count(*)::text FROM internal_quotes
    ORDER BY 1;
  "'
}

candidate_id=""
cleanup_candidate() {
  if [ -n "$candidate_id" ]; then
    echo "Deployment stopped before cutover completed; leaving API candidate $candidate_id running." >&2
    echo "After recovery, remove it with: docker rm -f $candidate_id" >&2
  fi
}
trap cleanup_candidate EXIT INT TERM

cd "$APP_DIR"

[ -f "$ENV_FILE" ] || fail "Missing $APP_DIR/$ENV_FILE"
[ -f "$COMPOSE_FILE" ] || fail "Missing $APP_DIR/$COMPOSE_FILE"
if grep -q "change-this-long-random-password" "$ENV_FILE"; then
  fail "$APP_DIR/$ENV_FILE still contains the example database password"
fi
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  fail "Tracked production files contain local changes; refusing to overwrite them"
fi

db_id="$(compose ps -q db)"
api_id="$(compose ps -q api)"
web_id="$(compose ps -q web)"
[ -n "$db_id" ] || fail "Database container is not running"
[ -n "$api_id" ] || fail "API container is not running"
[ -n "$web_id" ] || fail "Web container is not running"
[ "$(container_health "$db_id")" = "healthy" ] || fail "Database container is not healthy"
[ "$(container_health "$api_id")" = "healthy" ] || fail "API container is not healthy"
[ "$(container_health "$web_id")" = "healthy" ] || fail "Web container is not healthy"

old_commit="$(git rev-parse HEAD)"
git fetch --prune origin
target_commit="$(git rev-parse "$UPSTREAM")"

if [ "$old_commit" = "$target_commit" ]; then
  echo "Production is already at $target_commit"
  exit 0
fi
git merge-base --is-ancestor "$old_commit" "$target_commit" \
  || fail "Production HEAD cannot be fast-forwarded to $UPSTREAM"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
old_short="$(printf '%.7s' "$old_commit")"
target_short="$(printf '%.7s' "$target_commit")"
backup_dir="$BACKUP_ROOT/main-$old_short-to-$target_short-$timestamp"
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"

printf '%s\n' "$old_commit" > "$backup_dir/old-commit.txt"
printf '%s\n' "$target_commit" > "$backup_dir/target-commit.txt"
git diff --name-only "$old_commit" "$target_commit" > "$backup_dir/changed-files.txt"
cp "$ENV_FILE" "$backup_dir/environment.snapshot"
chmod 600 "$backup_dir/environment.snapshot"
cp "$COMPOSE_FILE" "$backup_dir/compose.snapshot.yml"
for snapshot_file in Dockerfile.backend Dockerfile.frontend nginx.prod.conf deploy/update-from-github.sh; do
  if [ -f "$snapshot_file" ]; then
    cp "$snapshot_file" "$backup_dir/$(basename "$snapshot_file").snapshot"
  fi
done

compose ps > "$backup_dir/containers-before.txt"
docker inspect "$db_id" "$api_id" "$web_id" > "$backup_dir/container-inspect-before.json"
capture_database_state > "$backup_dir/database-state-before.txt"
compose exec -T db sh -lc 'pg_dump --format=custom --username="$POSTGRES_USER" "$POSTGRES_DB"' \
  > "$backup_dir/database.dump"
(cd "$backup_dir" && sha256sum database.dump > database.dump.sha256 && sha256sum -c database.dump.sha256)
compose exec -T db pg_restore -l < "$backup_dir/database.dump" > "$backup_dir/database.restore-list.txt"

old_api_image="$(docker inspect --format '{{.Image}}' "$api_id")"
old_web_image="$(docker inspect --format '{{.Image}}' "$web_id")"
docker tag "$old_api_image" "rrnexus-api:rollback-$timestamp"
docker tag "$old_web_image" "rrnexus-web:rollback-$timestamp"

migration_changes="$(git diff --name-only "$old_commit" "$target_commit" -- backend/alembic/versions || true)"
git merge --ff-only "$target_commit"

echo "Building API and Web images while the current service remains online"
compose build api web

if [ -z "$migration_changes" ]; then
  network_name="$(docker inspect --format '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}}{{end}}' "$api_id")"
  [ -n "$network_name" ] || fail "Cannot determine the production Docker network"
  new_api_image_ref="$(docker inspect --format '{{.Config.Image}}' "$api_id")"
  new_api_image="$(docker image inspect --format '{{.Id}}' "$new_api_image_ref")"
  [ -n "$new_api_image" ] || fail "Cannot determine the newly built API image"
  candidate_name="rr-api-candidate-$timestamp"

  echo "Starting a health-checked API candidate before replacing the production API"
  candidate_id="$(docker run -d \
    --name "$candidate_name" \
    --env-file "$ENV_FILE" \
    --network "$network_name" \
    --network-alias api \
    "$new_api_image")"
  wait_for_healthy "$candidate_id" "API candidate"

  echo "Replacing Web first so it can dynamically resolve the healthy API pool"
  compose up -d --no-deps web
  web_id="$(compose ps -q web)"
  wait_for_healthy "$web_id" "Web"

  echo "Replacing the production API while the candidate continues serving requests"
  compose up -d --no-deps api
  api_id="$(compose ps -q api)"
  wait_for_healthy "$api_id" "API"

  docker rm -f "$candidate_id" >/dev/null
  candidate_id=""
else
  echo "Alembic migration changes detected; using the health-gated maintenance-window path"
  printf '%s\n' "$migration_changes"
  compose up -d --no-deps api
  api_id="$(compose ps -q api)"
  wait_for_healthy "$api_id" "API"
  compose up -d --no-deps web
  web_id="$(compose ps -q web)"
  wait_for_healthy "$web_id" "Web"
fi

curl --fail --silent --show-error --max-time 10 http://127.0.0.1/health > "$backup_dir/health.json"
curl --fail --silent --show-error --max-time 10 http://127.0.0.1/ > "$backup_dir/home.html"
compose ps > "$backup_dir/containers-after.txt"
docker inspect "$db_id" "$api_id" "$web_id" > "$backup_dir/container-inspect-after.json"
capture_database_state > "$backup_dir/database-state-after.txt"
diff -u "$backup_dir/database-state-before.txt" "$backup_dir/database-state-after.txt" \
  > "$backup_dir/database-state.diff" || true
(cd "$backup_dir" && sha256sum -c database.dump.sha256)

docker image prune -f >/dev/null
trap - EXIT INT TERM

echo "Deployment completed at $target_commit"
echo "Database container preserved: $db_id"
echo "Verified backup: $backup_dir/database.dump"
echo "Rollback images: rrnexus-api:rollback-$timestamp and rrnexus-web:rollback-$timestamp"
