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

capture_environment_manifest() {
  env_file="$1"
  manifest_path="$2"
  checksum_path="$3"

  # Backups must never duplicate runtime secret values. Record only valid
  # variable names and a checksum so operators can prove which unchanged
  # server-side secret file was used for the deployment.
  awk '
    {
      line = $0
      sub(/^[[:space:]]*export[[:space:]]+/, "", line)
      equals = index(line, "=")
      if (equals == 0) next
      key = substr(line, 1, equals - 1)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", key)
      if (key ~ /^[A-Za-z_][A-Za-z0-9_]*$/) print key
    }
  ' "$env_file" | LC_ALL=C sort -u > "$manifest_path"
  sha256sum "$env_file" | awk '{ print $1 "  runtime-environment" }' > "$checksum_path"
  chmod 600 "$manifest_path" "$checksum_path"
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

capture_container_metadata() {
  for container_id in "$@"; do
    docker inspect --format 'id={{.Id}}
name={{.Name}}
image={{.Image}}
config_image={{.Config.Image}}
created={{.Created}}
state={{.State.Status}}
health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}
restart_count={{.RestartCount}}
networks={{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}
mounts={{range .Mounts}}{{.Type}}:{{.Destination}} {{end}}
---' "$container_id"
  done
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

import_rootfs_rollback_image() {
  service_label="$1"
  rootfs_path="$2"
  rollback_tag="$3"

  case "$service_label" in
    api)
      docker import \
        --change 'ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1' \
        --change 'WORKDIR /app/backend' \
        --change 'EXPOSE 8000' \
        --change 'CMD ["sh", "-c", "alembic -c alembic.ini upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]' \
        "$rootfs_path" "$rollback_tag" >/dev/null
      ;;
    web)
      docker import \
        --change 'ENTRYPOINT ["/docker-entrypoint.sh"]' \
        --change 'CMD ["nginx", "-g", "daemon off;"]' \
        --change 'EXPOSE 80' \
        --change 'STOPSIGNAL SIGQUIT' \
        "$rootfs_path" "$rollback_tag" >/dev/null
      ;;
    *)
      fail "Unsupported rollback service: $service_label"
      ;;
  esac
}

create_rollback_artifact() {
  container_id="$1"
  service_label="$2"
  rollback_tag="$3"
  artifact_dir="$4"
  image_id="$(docker inspect --format '{{.Image}}' "$container_id")"
  record_path="$artifact_dir/${service_label}-rollback-artifact.txt"

  if docker image inspect "$image_id" >/dev/null 2>&1; then
    docker tag "$image_id" "$rollback_tag"
    {
      echo "service=$service_label"
      echo "kind=tagged-existing-image"
      echo "rollback_image=$rollback_tag"
      echo "source_image=$image_id"
    } > "$record_path"
    return
  fi

  rootfs_name="${service_label}-container-rootfs.tar"
  rootfs_path="$artifact_dir/$rootfs_name"
  metadata_path="$artifact_dir/${service_label}-container-metadata.txt"

  echo "$service_label image object $image_id is unavailable; exporting the running container rootfs"
  capture_container_metadata "$container_id" > "$metadata_path"
  docker export "$container_id" > "$rootfs_path"
  [ -s "$rootfs_path" ] || fail "$service_label container rootfs export is empty"
  (
    cd "$artifact_dir"
    sha256sum "$rootfs_name" > "$rootfs_name.sha256"
    sha256sum -c "$rootfs_name.sha256"
  )
  import_rootfs_rollback_image "$service_label" "$rootfs_path" "$rollback_tag"
  docker image inspect "$rollback_tag" >/dev/null

  {
    echo "service=$service_label"
    echo "kind=imported-rootfs-image"
    echo "rollback_image=$rollback_tag"
    echo "missing_source_image=$image_id"
    echo "rootfs=$rootfs_path"
    echo "rootfs_sha256=$rootfs_path.sha256"
    echo "container_metadata=$metadata_path"
  } > "$record_path"
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
ai_control_volume=""
ai_disable_marker_preexisting=0
ai_disable_marker_created=0
cleanup_candidate() {
  if [ -n "$candidate_id" ]; then
    echo "Deployment stopped before cutover completed; leaving API candidate $candidate_id running." >&2
    echo "After recovery, remove it with: docker rm -f $candidate_id" >&2
  fi
  if [ "$ai_disable_marker_created" -eq 1 ]; then
    echo "AI runtime disable marker remains active because deployment did not complete." >&2
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

ai_pilot_enabled="$(read_env_value AI_PILOT_ENABLED)"
case "$ai_pilot_enabled" in
  true)
    [ "$(read_env_value AI_RUNTIME_DISABLE_PATH)" = "/app/backend/control/ai.disabled" ] \
      || fail "AI Pilot requires the approved runtime disable path"
    ai_control_volume="$(
      docker inspect --format '{{range .Mounts}}{{if eq .Destination "/app/backend/control"}}{{.Name}}{{end}}{{end}}' "$api_id"
    )"
    [ -n "$ai_control_volume" ] || fail "AI Pilot control volume is not mounted"
    if docker run --rm --network none -v "$ai_control_volume:/control:ro" \
      postgres:16-alpine test -f /control/ai.disabled; then
      ai_disable_marker_preexisting=1
    fi
    ;;
  false|"") ;;
  *) fail "AI_PILOT_ENABLED must be true or false" ;;
esac

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
capture_environment_manifest \
  "$ENV_FILE" \
  "$backup_dir/environment.keys.txt" \
  "$backup_dir/environment.sha256"
cp "$COMPOSE_FILE" "$backup_dir/compose.snapshot.yml"
for snapshot_file in Dockerfile.backend Dockerfile.frontend nginx.prod.conf deploy/update-from-github.sh; do
  if [ -f "$snapshot_file" ]; then
    cp "$snapshot_file" "$backup_dir/$(basename "$snapshot_file").snapshot"
  fi
done

compose ps > "$backup_dir/containers-before.txt"
capture_container_metadata "$db_id" "$api_id" "$web_id" \
  > "$backup_dir/container-metadata-before.txt"
capture_database_state > "$backup_dir/database-state-before.txt"
compose exec -T db sh -lc 'pg_dump --format=custom --username="$POSTGRES_USER" "$POSTGRES_DB"' \
  > "$backup_dir/database.dump"
(cd "$backup_dir" && sha256sum database.dump > database.dump.sha256 && sha256sum -c database.dump.sha256)
compose exec -T db pg_restore -l < "$backup_dir/database.dump" > "$backup_dir/database.restore-list.txt"

create_rollback_artifact "$api_id" api "rrnexus-api:rollback-$timestamp" "$backup_dir"
create_rollback_artifact "$web_id" web "rrnexus-web:rollback-$timestamp" "$backup_dir"

migration_changes="$(git diff --name-only "$old_commit" "$target_commit" -- backend/alembic/versions || true)"
git merge --ff-only "$target_commit"

echo "Building API and Web images while the current service remains online"
compose build api web

if [ "$ai_pilot_enabled" = "true" ] && [ "$ai_disable_marker_preexisting" -eq 0 ]; then
  echo "Disabling AI at the shared runtime control boundary before API cutover"
  docker run --rm --network none -v "$ai_control_volume:/control" postgres:16-alpine \
    sh -c 'umask 077; : > /control/ai.disabled'
  ai_disable_marker_created=1
fi

if [ -z "$migration_changes" ] && [ "$ai_pilot_enabled" != "true" ]; then
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
    --volumes-from "$api_id" \
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
  echo "Using the health-gated single-API maintenance-window path"
  if [ -n "$migration_changes" ]; then
    echo "Alembic migration changes detected:"
    printf '%s\n' "$migration_changes"
  else
    echo "AI Pilot is enabled; avoiding concurrent in-process limiter instances"
  fi
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
capture_container_metadata "$db_id" "$api_id" "$web_id" \
  > "$backup_dir/container-metadata-after.txt"
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
echo "Rollback evidence: $backup_dir/api-rollback-artifact.txt and $backup_dir/web-rollback-artifact.txt"
if [ "$ai_disable_marker_created" -eq 1 ]; then
  echo "AI remains disabled by the runtime marker; run the two-stage Pilot readiness procedure before removing it."
fi
