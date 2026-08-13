from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Protocol

GuardDisableScope = Literal["GLOBAL", "FACTORY", "USER"]


class GuardBackendError(RuntimeError):
    """The selected shared state backend could not make a safe decision."""


class GuardBackendUnavailable(GuardBackendError):
    pass


class GuardBackendDecision(GuardBackendError):
    def __init__(
        self,
        *,
        code: str,
        retry_after_seconds: int | None = None,
        disabled_scope: GuardDisableScope | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.retry_after_seconds = retry_after_seconds
        self.disabled_scope = disabled_scope


@dataclass(frozen=True, slots=True)
class GuardAcquireRequest:
    user_id: str
    factory_id: str
    instance_id: str
    reservation_tokens: int
    budget_day: date
    now: datetime
    lease_seconds: int
    request_retention_minutes: int
    budget_retention_days: int
    max_concurrent_per_user: int
    requests_per_minute: int
    daily_token_budget: int


@dataclass(frozen=True, slots=True)
class GuardLeaseRecord:
    lease_id: str
    lease_token: str
    user_id: str
    factory_id: str
    instance_id: str
    reservation_tokens: int
    budget_day: date


class GuardStateBackend(Protocol):
    def require_enabled(
        self,
        *,
        user_id: str,
        factory_id: str,
        now: datetime,
    ) -> None: ...

    def acquire(self, request: GuardAcquireRequest) -> GuardLeaseRecord: ...

    def bind_factory(
        self,
        lease: GuardLeaseRecord,
        *,
        factory_id: str,
        now: datetime,
        lease_seconds: int,
    ) -> GuardLeaseRecord: ...

    def renew(
        self,
        lease: GuardLeaseRecord,
        *,
        now: datetime,
        lease_seconds: int,
    ) -> None: ...

    def mark_provider_started(
        self,
        lease: GuardLeaseRecord,
        *,
        now: datetime,
        lease_seconds: int,
    ) -> None: ...

    def record_usage(
        self,
        lease: GuardLeaseRecord,
        *,
        total_tokens: int,
        now: datetime,
        lease_seconds: int,
    ) -> None: ...

    def mark_completed(
        self,
        lease: GuardLeaseRecord,
        *,
        now: datetime,
        lease_seconds: int,
    ) -> None: ...

    def release(self, lease: GuardLeaseRecord, *, now: datetime) -> None: ...

    def snapshot(
        self,
        user_id: str,
        *,
        day: date,
        now: datetime,
    ) -> dict[str, int]: ...

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
    ) -> None: ...

    def cleanup(
        self,
        *,
        now: datetime,
        budget_retention_days: int,
    ) -> dict[str, int]: ...
