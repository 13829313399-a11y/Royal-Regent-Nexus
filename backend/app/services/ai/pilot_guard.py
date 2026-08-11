from __future__ import annotations

import re
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from math import ceil
from time import monotonic
from typing import Literal
from zoneinfo import ZoneInfo

from app.core.config import Settings
from app.schemas.ai import AIPageContextInput, AIServerPageContext
from app.services.ai.provider_factory import get_pilot_provider_status
from app.services.ai.runtime_gate import (
    is_ai_runtime_disabled,
    runtime_disable_control_configured,
)
from app.services.auth import ALLOWED_FACTORY_IDS, AuthContext

AIPilotStatus = Literal[
    "DISABLED",
    "TLS_REQUIRED",
    "CONTROL_REQUIRED",
    "PROVIDER_REQUIRED",
    "GRANTED",
]

_PILOT_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_RATE_WINDOW_SECONDS = 60.0
_MAX_RETRY_AFTER_SECONDS = 86_400
_MAX_TOOL_CALLS_PER_ROUND = 8
_SYSTEM_CONTEXT_RESERVATION_UNITS = 16_384
_TOOL_SCHEMA_RESERVATION_UNITS = 65_536
_PILOT_TIME_ZONE = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True, slots=True)
class AIPilotAccess:
    granted: bool
    status: AIPilotStatus
    read_only: Literal[True] = True


class AIPilotGuardError(RuntimeError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int,
        retryable: bool = False,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.retry_after_seconds = (
            min(max(retry_after_seconds, 1), _MAX_RETRY_AFTER_SECONDS)
            if retry_after_seconds is not None
            else None
        )

    def payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.retry_after_seconds is not None:
            payload["retry_after_seconds"] = self.retry_after_seconds
        return payload


@dataclass(slots=True)
class _UserRuntimeState:
    active_requests: int = 0
    request_times: deque[float] = field(default_factory=deque)


@dataclass(slots=True)
class _UserBudgetState:
    used_tokens: int = 0
    reserved_tokens: int = 0


@dataclass(slots=True)
class AIPilotLease:
    user_id: str
    reservation_tokens: int
    budget_day: date | None
    _guard: AIPilotGuard = field(repr=False)
    _tracked: bool = True
    _provider_started: bool = False
    _completed: bool = False
    _reported_tokens: int = 0
    _closed: bool = False

    def mark_provider_started(self) -> None:
        self._guard._mark_provider_started(self)

    def record_usage(self, total_tokens: int) -> None:
        self._guard._record_usage(self, total_tokens)

    def mark_completed(self) -> None:
        self._guard._mark_completed(self)

    def close(self) -> None:
        self._guard._release(self)


class AIPilotGuard:
    """Single-process Pilot authorization, rate, concurrency and usage guard.

    This state is intentionally in memory for the initial single-worker Pilot.
    It must be replaced by shared atomic storage before multiple workers or
    horizontally scaled API replicas are enabled.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] = monotonic,
        utcnow: Callable[[], datetime] | None = None,
    ) -> None:
        self._clock = clock
        self._utcnow = utcnow or (lambda: datetime.now(UTC))
        self._lock = threading.Lock()
        self._runtime: dict[str, _UserRuntimeState] = {}
        self._budgets: dict[tuple[str, date], _UserBudgetState] = {}

    @staticmethod
    def _configured_ids(raw: str) -> frozenset[str]:
        values = tuple(value.strip() for value in raw.split(",") if value.strip())
        if (
            not values
            or len(values) > 100
            or len(set(values)) != len(values)
            or any(_PILOT_ID_PATTERN.fullmatch(value) is None for value in values)
        ):
            raise AIPilotGuardError(
                code="AI_PILOT_ACCESS_DENIED",
                message="当前账号未开放 AI Pilot 权限。",
                status_code=403,
            )
        return frozenset(values)

    def _configured_scope(
        self,
        settings: Settings,
    ) -> tuple[frozenset[str], frozenset[str]]:
        user_ids = self._configured_ids(settings.ai_pilot_user_ids)
        factory_ids = self._configured_ids(settings.ai_pilot_factory_ids)
        if not factory_ids.issubset(ALLOWED_FACTORY_IDS):
            raise AIPilotGuardError(
                code="AI_PILOT_ACCESS_DENIED",
                message="当前账号未开放 AI Pilot 权限。",
                status_code=403,
            )
        return user_ids, factory_ids

    @staticmethod
    def _user_has_pilot_factory_scope(
        user: AuthContext,
        factory_ids: frozenset[str],
    ) -> bool:
        return "*" in user.factory_scopes or bool(
            factory_ids.intersection(user.factory_scopes)
        )

    def evaluate_access(
        self,
        user: AuthContext,
        settings: Settings,
    ) -> AIPilotAccess:
        if not settings.ai_pilot_enabled:
            raise AIPilotGuardError(
                code="AI_PILOT_ACCESS_DENIED",
                message="当前账号未开放 AI Pilot 权限。",
                status_code=403,
            )
        user_ids, factory_ids = self._configured_scope(settings)
        if user.id not in user_ids or not self._user_has_pilot_factory_scope(
            user,
            factory_ids,
        ):
            raise AIPilotGuardError(
                code="AI_PILOT_ACCESS_DENIED",
                message="当前账号未开放 AI Pilot 权限。",
                status_code=403,
            )
        if not settings.ai_enabled:
            return AIPilotAccess(granted=False, status="DISABLED")
        production = settings.app_env.strip().lower() in {"production", "prod"}
        if production and not runtime_disable_control_configured(settings):
            return AIPilotAccess(granted=False, status="CONTROL_REQUIRED")
        if is_ai_runtime_disabled(settings):
            return AIPilotAccess(granted=False, status="DISABLED")
        if production and not settings.ai_pilot_public_tls_verified:
            return AIPilotAccess(granted=False, status="TLS_REQUIRED")
        if production:
            provider_status = get_pilot_provider_status(settings)
            if not provider_status.available:
                return AIPilotAccess(granted=False, status="PROVIDER_REQUIRED")
        return AIPilotAccess(granted=True, status="GRANTED")

    def require_factory_access(
        self,
        *,
        user: AuthContext,
        requested_context: AIPageContextInput | None,
        server_context: AIServerPageContext | None,
        settings: Settings,
    ) -> None:
        requested_factory_id = (
            requested_context.factory_id if requested_context is not None else None
        )
        _, factory_ids = self._configured_scope(settings)
        if requested_factory_id is None:
            if not self._user_has_pilot_factory_scope(user, factory_ids):
                raise AIPilotGuardError(
                    code="AI_PILOT_ACCESS_DENIED",
                    message="当前账号或厂区未开放 AI Pilot 权限。",
                    status_code=403,
                )
            return
        if (
            requested_factory_id not in factory_ids
            or not isinstance(server_context, AIServerPageContext)
            or server_context.verified_factory_id != requested_factory_id
        ):
            raise AIPilotGuardError(
                code="AI_PILOT_ACCESS_DENIED",
                message="当前账号或厂区未开放 AI Pilot 权限。",
                status_code=403,
            )

    @staticmethod
    def reservation_tokens(
        *,
        input_chars: int,
        has_attachments: bool,
        settings: Settings,
    ) -> int:
        safe_input_chars = max(input_chars, 0)
        if has_attachments:
            return (
                safe_input_chars
                + settings.ai_max_image_total_bytes
                + settings.ai_pilot_max_output_tokens
                + _SYSTEM_CONTEXT_RESERVATION_UNITS
            )

        tool_rounds = settings.ai_max_tool_rounds
        provider_calls = tool_rounds + 1
        replay_factor = tool_rounds * (tool_rounds + 1) // 2
        repeated_prompt_budget = provider_calls * (
            safe_input_chars
            + settings.ai_max_input_message_chars
            + _SYSTEM_CONTEXT_RESERVATION_UNITS
            + _TOOL_SCHEMA_RESERVATION_UNITS
        )
        # Every prior tool result is replayed on subsequent Provider rounds.
        # The triangular factor reserves the maximum repeated JSON footprint.
        repeated_tool_result_budget = (
            replay_factor
            * _MAX_TOOL_CALLS_PER_ROUND
            * settings.ai_max_tool_result_bytes
        )
        # All arguments emitted in one Provider round share that round's
        # output ceiling, then remain in every subsequent transcript.
        repeated_tool_argument_budget = (
            replay_factor * settings.ai_pilot_max_output_tokens
        )
        return (
            repeated_prompt_budget
            + repeated_tool_result_budget
            + repeated_tool_argument_budget
            + provider_calls * settings.ai_pilot_max_output_tokens
        )

    def acquire(
        self,
        *,
        user: AuthContext,
        settings: Settings,
        input_chars: int,
        has_attachments: bool,
    ) -> AIPilotLease:
        access = self.evaluate_access(user, settings)
        if access.status == "DISABLED":
            if settings.ai_enabled:
                raise AIPilotGuardError(
                    code="AI_DISABLED",
                    message="AI 功能当前已由运行时开关关闭。",
                    status_code=503,
                )
            return AIPilotLease(
                user_id=user.id,
                reservation_tokens=0,
                budget_day=None,
                _guard=self,
                _tracked=False,
            )
        if not access.granted:
            raise AIPilotGuardError(
                code="AI_PILOT_ACCESS_DENIED",
                message="AI Pilot 尚未通过安全上线检查。",
                status_code=403,
            )

        now = self._clock()
        today = self._utcnow().astimezone(_PILOT_TIME_ZONE).date()
        reservation = self.reservation_tokens(
            input_chars=input_chars,
            has_attachments=has_attachments,
            settings=settings,
        )
        with self._lock:
            runtime = self._runtime.setdefault(user.id, _UserRuntimeState())
            cutoff = now - _RATE_WINDOW_SECONDS
            while runtime.request_times and runtime.request_times[0] <= cutoff:
                runtime.request_times.popleft()

            if runtime.active_requests >= settings.ai_pilot_max_concurrent_per_user:
                raise AIPilotGuardError(
                    code="AI_CONCURRENT_REQUEST_LIMIT",
                    message="当前已有 AI 请求正在处理，请稍后再试。",
                    status_code=429,
                    retryable=True,
                    retry_after_seconds=1,
                )
            if len(runtime.request_times) >= settings.ai_pilot_requests_per_minute:
                retry_after = ceil(
                    max(1.0, runtime.request_times[0] + _RATE_WINDOW_SECONDS - now)
                )
                raise AIPilotGuardError(
                    code="AI_RATE_LIMITED",
                    message="AI 请求过于频繁，请稍后重试。",
                    status_code=429,
                    retryable=True,
                    retry_after_seconds=retry_after,
                )

            budget = self._budgets.setdefault(
                (user.id, today),
                _UserBudgetState(),
            )
            if (
                budget.used_tokens + budget.reserved_tokens + reservation
                > settings.ai_pilot_daily_token_budget
            ):
                next_day = datetime.combine(
                    today + timedelta(days=1),
                    datetime.min.time(),
                    tzinfo=_PILOT_TIME_ZONE,
                )
                retry_after = int(
                    max(
                        1.0,
                        (
                            next_day - self._utcnow().astimezone(_PILOT_TIME_ZONE)
                        ).total_seconds(),
                    )
                )
                raise AIPilotGuardError(
                    code="AI_BUDGET_EXCEEDED",
                    message="今日 AI 使用预算已达到上限，请稍后再试。",
                    status_code=429,
                    retryable=True,
                    retry_after_seconds=retry_after,
                )

            runtime.active_requests += 1
            runtime.request_times.append(now)
            budget.reserved_tokens += reservation
            self._drop_stale_budgets(today)

        return AIPilotLease(
            user_id=user.id,
            reservation_tokens=reservation,
            budget_day=today,
            _guard=self,
        )

    def _drop_stale_budgets(self, today: date) -> None:
        stale = [
            key
            for key, value in self._budgets.items()
            if key[1] < today and value.reserved_tokens == 0
        ]
        for key in stale:
            del self._budgets[key]

    def _mark_provider_started(self, lease: AIPilotLease) -> None:
        with self._lock:
            if not lease._closed:
                lease._provider_started = True

    def _record_usage(self, lease: AIPilotLease, total_tokens: int) -> None:
        if not isinstance(total_tokens, int) or total_tokens < 0:
            return
        with self._lock:
            if not lease._closed:
                lease._reported_tokens += total_tokens

    def _mark_completed(self, lease: AIPilotLease) -> None:
        with self._lock:
            if not lease._closed:
                lease._completed = True

    def _release(self, lease: AIPilotLease) -> None:
        with self._lock:
            if lease._closed:
                return
            lease._closed = True
            if not lease._tracked or lease.budget_day is None:
                return
            runtime = self._runtime.get(lease.user_id)
            if runtime is not None:
                runtime.active_requests = max(0, runtime.active_requests - 1)
            budget = self._budgets.get((lease.user_id, lease.budget_day))
            if budget is None:
                return
            budget.reserved_tokens = max(
                0,
                budget.reserved_tokens - lease.reservation_tokens,
            )
            if lease._completed:
                budget.used_tokens += (
                    lease._reported_tokens
                    if lease._reported_tokens > 0
                    else lease.reservation_tokens
                )
            elif lease._provider_started:
                budget.used_tokens += max(
                    lease.reservation_tokens,
                    lease._reported_tokens,
                )

    def snapshot(self, user_id: str, *, day: date | None = None) -> dict[str, int]:
        """Return metadata-only state for focused tests and internal diagnostics."""

        target_day = day or self._utcnow().astimezone(_PILOT_TIME_ZONE).date()
        with self._lock:
            runtime = self._runtime.get(user_id, _UserRuntimeState())
            budget = self._budgets.get((user_id, target_day), _UserBudgetState())
            return {
                "active_requests": runtime.active_requests,
                "requests_in_window": len(runtime.request_times),
                "used_tokens": budget.used_tokens,
                "reserved_tokens": budget.reserved_tokens,
            }
