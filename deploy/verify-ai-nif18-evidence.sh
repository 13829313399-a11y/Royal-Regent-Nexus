#!/usr/bin/env sh
set -eu
export LC_ALL=C

EVIDENCE_FILE="${NIF18_EVIDENCE_FILE:-}"
UPSTREAM_REF="${UPSTREAM_REF:-origin/main}"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

read_evidence_value() {
  key="$1"
  awk -v wanted="$key" '
    {
      line = $0
      if (line ~ /^[[:space:]]*#/ || line ~ /^[[:space:]]*$/) next
      equals = index(line, "=")
      if (equals == 0) next
      candidate = substr(line, 1, equals - 1)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", candidate)
      if (candidate == wanted) value = substr(line, equals + 1)
    }
    END { print value }
  ' "$EVIDENCE_FILE" | tr -d '\r'
}

require_exact() {
  key="$1"
  expected="$2"
  actual="$(read_evidence_value "$key")"
  [ "$actual" = "$expected" ] || fail "$key is not the required $expected result"
}

require_nonempty() {
  key="$1"
  actual="$(read_evidence_value "$key")"
  [ -n "$actual" ] || fail "$key is missing"
  [ "${#actual}" -le 160 ] || fail "$key exceeds the evidence length limit"
  case "$actual" in
    *'='*|*'`'*|'$('*|*'-----BEGIN '*) fail "$key contains prohibited secret-like syntax" ;;
  esac
}

[ -n "$EVIDENCE_FILE" ] || fail "NIF18_EVIDENCE_FILE is required"
[ -f "$EVIDENCE_FILE" ] || fail "NIF-18 evidence file is unavailable"

# Evidence is metadata only. Secret values, cookies and connection strings are
# prohibited even if an operator accidentally adds an unrecognized key.
if grep -Eiq '(password|secret|api[_-]?key|cookie|authorization|database_url)[[:space:]]*=' "$EVIDENCE_FILE"; then
  fail "NIF-18 evidence must not contain credentials or cookies"
fi

require_exact NIF18_SCHEMA_VERSION nif18-production-evidence-v1
require_exact OVERALL_RESULT PASS
for gate in \
  GIT_GATE \
  MIGRATION_GATE \
  TLS_HSTS_GATE \
  SESSION_GATE \
  SECRET_ROTATION_GATE \
  IAM_PILOT_GATE \
  PROVIDER_REGION_GATE \
  SHARED_GUARD_GATE \
  MULTI_INSTANCE_GATE \
  KILL_SWITCH_GATE \
  PROVIDER_FAULT_GATE \
  WORKER_RECOVERY_GATE \
  DATABASE_BACKUP_RESTORE_GATE \
  ARTIFACT_OPERATIONS_GATE \
  EVIDENCE_REAUTH_GATE \
  CONTROLLED_APPLY_DRAFT_GATE \
  BUSINESS_FAILURE_ISOLATION_GATE \
  BROWSER_ACCEPTANCE_GATE \
  ROLLBACK_GATE \
  COST_ALERT_GATE
do
  require_exact "$gate" PASS
done

for field in \
  DEPLOYED_REVISION \
  EXECUTED_AT_UTC \
  PILOT_USER_SET_REF \
  PILOT_FACTORY_SET_REF \
  BACKUP_EVIDENCE_REF \
  RESTORE_DRILL_REF \
  FAULT_DRILL_REF \
  BROWSER_EVIDENCE_REF \
  COST_ALERT_REF \
  PRODUCT_APPROVER \
  SECURITY_APPROVER \
  OPERATIONS_APPROVER
do
  require_nonempty "$field"
done

deployed_revision="$(read_evidence_value DEPLOYED_REVISION)"
case "$deployed_revision" in
  *[!0-9a-f]*|'') fail "DEPLOYED_REVISION must be a lowercase Git SHA" ;;
esac
[ "${#deployed_revision}" -eq 40 ] || fail "DEPLOYED_REVISION must be a full Git SHA"

current_revision="$(git rev-parse HEAD)"
[ "$deployed_revision" = "$current_revision" ] \
  || fail "evidence revision does not match the checked-out revision"
[ -z "$(git status --porcelain --untracked-files=no)" ] \
  || fail "tracked production files are not clean"
git rev-parse --verify "$UPSTREAM_REF" >/dev/null 2>&1 \
  || fail "UPSTREAM_REF is unavailable"
git merge-base --is-ancestor "$current_revision" "$UPSTREAM_REF" \
  || fail "checked-out revision is not fast-forward compatible with UPSTREAM_REF"

echo "NIF-18 production evidence passed for revision $current_revision."
