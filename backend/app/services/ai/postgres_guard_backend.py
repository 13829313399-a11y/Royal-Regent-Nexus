from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from math import ceil
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.ai_guard import (
    AIGuardDailyBudget,
    AIGuardDisableState,
    AIGuardLease,
    AIGuardRequestEvent,
)
from app.services.ai.guard_backend import (
    GuardAcquireRequest,
    GuardBackendDecision,
    GuardBackendUnavailable,
    GuardDisableScope,
    GuardLeaseRecord,
)

_GLOBAL_SCOPE_ID = "*"
_RATE_WINDOW_SECONDS = 60
_SQLITE_TEST_LOCK = threading.RLock()
_PILOT_TIME_ZONE = ZoneInfo("Asia/Shanghai")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _time_text(value: datetime) -> str:
    return _utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _advisory_key(value: str) -> int:
    raw = hashlib.blake2b(value.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(raw, byteorder="big", signed=True)


class PostgreSQLGuardBackend:
    """Atomic metadata-only Guard state for PostgreSQL.

    SQLite support exists only for deterministic unit tests. Runtime selection of
    this backend validates PostgreSQL and never silently uses the test path.
    """

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        allow_sqlite_for_tests: bool = False,
    ) -> None:
        self._session_factory = session_factory
        self._allow_sqlite_for_tests = allow_sqlite_for_tests

    def _dialect(self, db: Session) -> str:
        dialect = db.get_bind().dialect.name
        if dialect != "postgresql" and not (
            self._allow_sqlite_for_tests and dialect == "sqlite"
        ):
            raise GuardBackendUnavailable(
                "shared AI Guard requires PostgreSQL"
            )
        return dialect

    def _lock_scopes(
        self,
        db: Session,
        *,
        user_id: str = "",
        factory_id: str = "",
    ) -> None:
        if self._dialect(db) != "postgresql":
            return
        keys = ["GLOBAL:*"]
        if factory_id:
            keys.append(f"FACTORY:{factory_id}")
        if user_id:
            keys.append(f"USER:{user_id}")
        for key in keys:
            db.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)"),
                {"lock_key": _advisory_key(key)},
            )

    def _run(self, operation):
        try:
            with _SQLITE_TEST_LOCK, self._session_factory() as db, db.begin():
                self._dialect(db)
                return operation(db)
        except GuardBackendDecision:
            raise
        except GuardBackendUnavailable:
            raise
        except SQLAlchemyError as exc:
            raise GuardBackendUnavailable(
                "shared AI Guard database operation failed"
            ) from exc

    @staticmethod
    def _disable_keys(
        *, user_id: str, factory_id: str
    ) -> tuple[tuple[GuardDisableScope, str], ...]:
        keys: list[tuple[GuardDisableScope, str]] = [("GLOBAL", _GLOBAL_SCOPE_ID)]
        if factory_id:
            keys.append(("FACTORY", factory_id))
        keys.append(("USER", user_id))
        return tuple(keys)

    def _require_enabled_locked(
        self,
        db: Session,
        *,
        user_id: str,
        factory_id: str,
        now_text: str,
    ) -> None:
        for scope_type, scope_id in self._disable_keys(
            user_id=user_id,
            factory_id=factory_id,
        ):
            state = db.get(AIGuardDisableState, (scope_type, scope_id))
            if state is not None and state.expires_at and state.expires_at <= now_text:
                db.delete(state)
                continue
            if (
                state is not None
                and state.disabled
                and (not state.expires_at or state.expires_at > now_text)
            ):
                raise GuardBackendDecision(
                    code="AI_DISABLED",
                    disabled_scope=scope_type,
                )

    @staticmethod
    def _charge_expired_lease(
        db: Session,
        lease: AIGuardLease,
        *,
        now_text: str,
    ) -> None:
        budget = db.get(
            AIGuardDailyBudget,
            (lease.user_id, lease.budget_day),
        )
        if budget is not None:
            budget.reserved_tokens = max(
                0,
                budget.reserved_tokens - lease.reservation_tokens,
            )
            if lease.completed:
                budget.used_tokens += (
                    lease.reported_tokens
                    if lease.reported_tokens > 0
                    else lease.reservation_tokens
                )
            elif lease.provider_started:
                budget.used_tokens += max(
                    lease.reservation_tokens,
                    lease.reported_tokens,
                )
            budget.updated_at = now_text
        db.delete(lease)

    def _expire_user_leases(
        self,
        db: Session,
        *,
        user_id: str,
        now_text: str,
    ) -> int:
        leases = db.scalars(
            select(AIGuardLease)
            .where(
                AIGuardLease.user_id == user_id,
                AIGuardLease.expires_at <= now_text,
            )
            .with_for_update()
        ).all()
        for lease in leases:
            self._charge_expired_lease(db, lease, now_text=now_text)
        return len(leases)

    def require_enabled(
        self,
        *,
        user_id: str,
        factory_id: str,
        now: datetime,
    ) -> None:
        now_text = _time_text(now)

        def operation(db: Session) -> None:
            self._lock_scopes(db, user_id=user_id, factory_id=factory_id)
            self._require_enabled_locked(
                db,
                user_id=user_id,
                factory_id=factory_id,
                now_text=now_text,
            )

        self._run(operation)

    def acquire(self, request: GuardAcquireRequest) -> GuardLeaseRecord:
        now = _utc(request.now)
        now_text = _time_text(now)
        cutoff_text = _time_text(now - timedelta(seconds=_RATE_WINDOW_SECONDS))
        event_expiry = _time_text(
            now + timedelta(minutes=request.request_retention_minutes)
        )
        lease_expiry = _time_text(now + timedelta(seconds=request.lease_seconds))

        def operation(db: Session) -> GuardLeaseRecord:
            self._lock_scopes(
                db,
                user_id=request.user_id,
                factory_id=request.factory_id,
            )
            self._expire_user_leases(
                db,
                user_id=request.user_id,
                now_text=now_text,
            )
            db.flush()
            db.execute(
                delete(AIGuardRequestEvent).where(
                    AIGuardRequestEvent.user_id == request.user_id,
                    AIGuardRequestEvent.expires_at <= now_text,
                )
            )
            budget_cutoff = (
                request.budget_day - timedelta(days=request.budget_retention_days)
            ).isoformat()
            db.execute(
                delete(AIGuardDailyBudget).where(
                    AIGuardDailyBudget.user_id == request.user_id,
                    AIGuardDailyBudget.budget_day < budget_cutoff,
                    AIGuardDailyBudget.reserved_tokens == 0,
                )
            )
            self._require_enabled_locked(
                db,
                user_id=request.user_id,
                factory_id=request.factory_id,
                now_text=now_text,
            )
            active_count = int(
                db.scalar(
                    select(func.count())
                    .select_from(AIGuardLease)
                    .where(
                        AIGuardLease.user_id == request.user_id,
                        AIGuardLease.expires_at > now_text,
                    )
                )
                or 0
            )
            if active_count >= request.max_concurrent_per_user:
                raise GuardBackendDecision(
                    code="AI_CONCURRENT_REQUEST_LIMIT",
                    retry_after_seconds=1,
                )

            request_times = tuple(
                db.scalars(
                    select(AIGuardRequestEvent.created_at)
                    .where(
                        AIGuardRequestEvent.user_id == request.user_id,
                        AIGuardRequestEvent.created_at > cutoff_text,
                    )
                    .order_by(AIGuardRequestEvent.created_at.asc())
                )
            )
            if len(request_times) >= request.requests_per_minute:
                retry_after = ceil(
                    max(
                        1.0,
                        (
                            _parse_time(request_times[0])
                            + timedelta(seconds=_RATE_WINDOW_SECONDS)
                            - now
                        ).total_seconds(),
                    )
                )
                raise GuardBackendDecision(
                    code="AI_RATE_LIMITED",
                    retry_after_seconds=retry_after,
                )

            budget_key = (request.user_id, request.budget_day.isoformat())
            budget = db.get(AIGuardDailyBudget, budget_key)
            if budget is None:
                budget = AIGuardDailyBudget(
                    user_id=request.user_id,
                    budget_day=request.budget_day.isoformat(),
                    used_tokens=0,
                    reserved_tokens=0,
                    updated_at=now_text,
                )
                db.add(budget)
                db.flush()
            if (
                budget.used_tokens
                + budget.reserved_tokens
                + request.reservation_tokens
                > request.daily_token_budget
            ):
                raise GuardBackendDecision(code="AI_BUDGET_EXCEEDED")

            lease = AIGuardLease(
                id=uuid4().hex,
                lease_token=uuid4().hex,
                user_id=request.user_id,
                factory_id=request.factory_id,
                instance_id=request.instance_id,
                reservation_tokens=request.reservation_tokens,
                budget_day=request.budget_day.isoformat(),
                expires_at=lease_expiry,
                provider_started=False,
                completed=False,
                reported_tokens=0,
                created_at=now_text,
                updated_at=now_text,
            )
            db.add(lease)
            db.add(
                AIGuardRequestEvent(
                    id=uuid4().hex,
                    user_id=request.user_id,
                    factory_id=request.factory_id,
                    instance_id=request.instance_id,
                    created_at=now_text,
                    expires_at=event_expiry,
                )
            )
            budget.reserved_tokens += request.reservation_tokens
            budget.updated_at = now_text
            return GuardLeaseRecord(
                lease_id=lease.id,
                lease_token=lease.lease_token,
                user_id=lease.user_id,
                factory_id=lease.factory_id,
                instance_id=lease.instance_id,
                reservation_tokens=lease.reservation_tokens,
                budget_day=request.budget_day,
            )

        return self._run(operation)

    def _update_lease(
        self,
        lease: GuardLeaseRecord,
        *,
        now: datetime,
        lease_seconds: int,
        provider_started: bool = False,
        usage_delta: int = 0,
        completed: bool = False,
    ) -> None:
        now_text = _time_text(now)
        expiry_text = _time_text(_utc(now) + timedelta(seconds=lease_seconds))

        def operation(db: Session) -> None:
            self._lock_scopes(
                db,
                user_id=lease.user_id,
                factory_id=lease.factory_id,
            )
            self._require_enabled_locked(
                db,
                user_id=lease.user_id,
                factory_id=lease.factory_id,
                now_text=now_text,
            )
            row = db.scalar(
                select(AIGuardLease)
                .where(
                    AIGuardLease.id == lease.lease_id,
                    AIGuardLease.lease_token == lease.lease_token,
                    AIGuardLease.instance_id == lease.instance_id,
                )
                .with_for_update()
            )
            if row is None or row.expires_at <= now_text:
                if row is not None:
                    self._charge_expired_lease(db, row, now_text=now_text)
                raise GuardBackendDecision(code="AI_GUARD_LEASE_LOST")
            if provider_started:
                row.provider_started = True
            if usage_delta:
                row.reported_tokens += usage_delta
            if completed:
                row.completed = True
            row.expires_at = expiry_text
            row.updated_at = now_text

        self._run(operation)

    def bind_factory(
        self,
        lease: GuardLeaseRecord,
        *,
        factory_id: str,
        now: datetime,
        lease_seconds: int,
    ) -> GuardLeaseRecord:
        if lease.factory_id == factory_id:
            self.renew(lease, now=now, lease_seconds=lease_seconds)
            return lease
        now_text = _time_text(now)
        expiry_text = _time_text(_utc(now) + timedelta(seconds=lease_seconds))

        def operation(db: Session) -> GuardLeaseRecord:
            self._lock_scopes(
                db,
                user_id=lease.user_id,
                factory_id=factory_id,
            )
            self._require_enabled_locked(
                db,
                user_id=lease.user_id,
                factory_id=factory_id,
                now_text=now_text,
            )
            row = db.scalar(
                select(AIGuardLease)
                .where(
                    AIGuardLease.id == lease.lease_id,
                    AIGuardLease.lease_token == lease.lease_token,
                    AIGuardLease.instance_id == lease.instance_id,
                )
                .with_for_update()
            )
            if row is None or row.expires_at <= now_text:
                if row is not None:
                    self._charge_expired_lease(db, row, now_text=now_text)
                raise GuardBackendDecision(code="AI_GUARD_LEASE_LOST")
            if row.factory_id and row.factory_id != factory_id:
                raise GuardBackendDecision(code="AI_GUARD_LEASE_LOST")
            row.factory_id = factory_id
            row.expires_at = expiry_text
            row.updated_at = now_text
            return GuardLeaseRecord(
                lease_id=lease.lease_id,
                lease_token=lease.lease_token,
                user_id=lease.user_id,
                factory_id=factory_id,
                instance_id=lease.instance_id,
                reservation_tokens=lease.reservation_tokens,
                budget_day=lease.budget_day,
            )

        return self._run(operation)

    def renew(
        self,
        lease: GuardLeaseRecord,
        *,
        now: datetime,
        lease_seconds: int,
    ) -> None:
        self._update_lease(lease, now=now, lease_seconds=lease_seconds)

    def mark_provider_started(
        self,
        lease: GuardLeaseRecord,
        *,
        now: datetime,
        lease_seconds: int,
    ) -> None:
        self._update_lease(
            lease,
            now=now,
            lease_seconds=lease_seconds,
            provider_started=True,
        )

    def record_usage(
        self,
        lease: GuardLeaseRecord,
        *,
        total_tokens: int,
        now: datetime,
        lease_seconds: int,
    ) -> None:
        self._update_lease(
            lease,
            now=now,
            lease_seconds=lease_seconds,
            usage_delta=total_tokens,
        )

    def mark_completed(
        self,
        lease: GuardLeaseRecord,
        *,
        now: datetime,
        lease_seconds: int,
    ) -> None:
        self._update_lease(
            lease,
            now=now,
            lease_seconds=lease_seconds,
            completed=True,
        )

    def release(self, lease: GuardLeaseRecord, *, now: datetime) -> None:
        now_text = _time_text(now)

        def operation(db: Session) -> None:
            self._lock_scopes(
                db,
                user_id=lease.user_id,
                factory_id=lease.factory_id,
            )
            row = db.scalar(
                select(AIGuardLease)
                .where(
                    AIGuardLease.id == lease.lease_id,
                    AIGuardLease.lease_token == lease.lease_token,
                    AIGuardLease.instance_id == lease.instance_id,
                )
                .with_for_update()
            )
            if row is None:
                return
            self._charge_expired_lease(db, row, now_text=now_text)

        self._run(operation)

    def snapshot(
        self,
        user_id: str,
        *,
        day: date,
        now: datetime,
    ) -> dict[str, int]:
        now_text = _time_text(now)
        cutoff_text = _time_text(_utc(now) - timedelta(seconds=_RATE_WINDOW_SECONDS))

        def operation(db: Session) -> dict[str, int]:
            self._lock_scopes(db, user_id=user_id)
            self._expire_user_leases(db, user_id=user_id, now_text=now_text)
            budget = db.get(AIGuardDailyBudget, (user_id, day.isoformat()))
            return {
                "active_requests": int(
                    db.scalar(
                        select(func.count())
                        .select_from(AIGuardLease)
                        .where(
                            AIGuardLease.user_id == user_id,
                            AIGuardLease.expires_at > now_text,
                        )
                    )
                    or 0
                ),
                "requests_in_window": int(
                    db.scalar(
                        select(func.count())
                        .select_from(AIGuardRequestEvent)
                        .where(
                            AIGuardRequestEvent.user_id == user_id,
                            AIGuardRequestEvent.created_at > cutoff_text,
                        )
                    )
                    or 0
                ),
                "used_tokens": budget.used_tokens if budget is not None else 0,
                "reserved_tokens": (
                    budget.reserved_tokens if budget is not None else 0
                ),
            }

        return self._run(operation)

    def set_disable_state(
        self,
        *,
        scope_type: GuardDisableScope,
        scope_id: str,
        disabled: bool,
        reason_code: str,
        expires_at: datetime | None,
        instance_id: str,
        now: datetime,
    ) -> None:
        normalized_scope_id = _GLOBAL_SCOPE_ID if scope_type == "GLOBAL" else scope_id
        if not normalized_scope_id:
            raise ValueError("disable scope id is required")
        now_text = _time_text(now)

        def operation(db: Session) -> None:
            self._lock_scopes(
                db,
                user_id=normalized_scope_id if scope_type == "USER" else "",
                factory_id=normalized_scope_id if scope_type == "FACTORY" else "",
            )
            row = db.get(AIGuardDisableState, (scope_type, normalized_scope_id))
            if row is None:
                row = AIGuardDisableState(
                    scope_type=scope_type,
                    scope_id=normalized_scope_id,
                    disabled=disabled,
                    reason_code=reason_code,
                    expires_at=_time_text(expires_at) if expires_at else "",
                    updated_by_instance=instance_id,
                    updated_at=now_text,
                )
                db.add(row)
                return
            row.disabled = disabled
            row.reason_code = reason_code
            row.expires_at = _time_text(expires_at) if expires_at else ""
            row.updated_by_instance = instance_id
            row.updated_at = now_text

        self._run(operation)

    def cleanup(
        self,
        *,
        now: datetime,
        budget_retention_days: int,
    ) -> dict[str, int]:
        now_text = _time_text(now)
        budget_cutoff = (
            _utc(now).astimezone(_PILOT_TIME_ZONE).date()
            - timedelta(days=budget_retention_days)
        ).isoformat()

        def operation(db: Session) -> dict[str, int]:
            self._lock_scopes(db)
            expired_leases = db.scalars(
                select(AIGuardLease)
                .where(AIGuardLease.expires_at <= now_text)
                .with_for_update()
            ).all()
            for lease in expired_leases:
                self._charge_expired_lease(db, lease, now_text=now_text)
            db.flush()
            requests = db.execute(
                delete(AIGuardRequestEvent).where(
                    AIGuardRequestEvent.expires_at <= now_text
                )
            ).rowcount
            budgets = db.execute(
                delete(AIGuardDailyBudget).where(
                    AIGuardDailyBudget.budget_day < budget_cutoff,
                    AIGuardDailyBudget.reserved_tokens == 0,
                )
            ).rowcount
            disable_states = db.execute(
                delete(AIGuardDisableState).where(
                    AIGuardDisableState.expires_at != "",
                    AIGuardDisableState.expires_at <= now_text,
                )
            ).rowcount
            return {
                "expired_leases": len(expired_leases),
                "request_events": int(requests or 0),
                "daily_budgets": int(budgets or 0),
                "disable_states": int(disable_states or 0),
            }

        return self._run(operation)
