import asyncio
import json
import logging
import threading
import time
from collections.abc import Callable
from types import SimpleNamespace

import pytest
from pydantic import Field
from sqlalchemy.exc import OperationalError

from app.core.config import Settings
from app.models.auth import AuthUser
from app.schemas.ai import (
    AIServerPageContext,
    AIToolErrorCode,
    AIToolRiskLevel,
    StrictToolInput,
)
from app.services.ai.providers import ProviderToolCall
from app.services.ai.tool_executor import ToolExecutionContext, ToolExecutor
from app.services.ai.tool_registry import (
    ToolRegistry,
    ToolSpec,
    build_default_tool_registry,
)
from app.services.auth import (
    AuthContext,
    AuthGrantContext,
    AuthOverrideContext,
    AuthProfileContext,
)


class FactoryArguments(StrictToolInput):
    factory_id: str = Field(min_length=1, max_length=32)
    note: str = Field(default="", max_length=16)


class FakeAuditDb:
    def __init__(self) -> None:
        self.records: list[object] = []
        self.commits = 0
        self.rollbacks = 0

    def add(self, value: object) -> None:
        self.records.append(value)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class ManagedSession(FakeAuditDb):
    def __init__(self) -> None:
        super().__init__()
        self.closed = 0
        self.lifecycle: list[tuple[str, int]] = []

    def rollback(self) -> None:
        self.lifecycle.append(("rollback", threading.get_ident()))
        super().rollback()

    def commit(self) -> None:
        self.lifecycle.append(("commit", threading.get_ident()))
        super().commit()

    def close(self) -> None:
        self.lifecycle.append(("close", threading.get_ident()))
        self.closed += 1


class PostgresManagedSession(ManagedSession):
    def __init__(self) -> None:
        super().__init__()
        self.statements: list[tuple[str, dict[str, object]]] = []

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    def execute(self, statement, parameters):
        self.lifecycle.append(("statement_timeout", threading.get_ident()))
        self.statements.append((str(statement), dict(parameters)))


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "ai_max_tool_result_rows": 50,
        "ai_max_tool_result_bytes": 65_536,
        "ai_max_tool_result_fields": 64,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def user_context(
    *,
    factory_id: str = "huaxing",
    overrides: tuple[AuthOverrideContext, ...] = (),
    profile: AuthProfileContext | None = None,
) -> AuthContext:
    grant = AuthGrantContext(
        role_id="role-reader",
        role_name="排产读取",
        factory_id=factory_id,
        department="production",
        permissions=frozenset({"injection_scheduling:read"}),
        binding_id=f"grant-{factory_id}",
    )
    return AuthContext(
        id="user-security",
        username="private-username",
        display_name="安全测试用户",
        roles=("测试角色",),
        role_codes=("test",),
        permissions=frozenset({"injection_scheduling:read"}),
        factory_scopes=(factory_id,),
        department_scopes=("production",),
        grants=(grant,),
        profile=profile,
        overrides=overrides,
        active_permission_codes=frozenset({"injection_scheduling:read"}),
    )


def scheduling_page_context(
    *,
    allowed_tool_groups: tuple[str, ...] = ("injection_scheduling",),
) -> AIServerPageContext:
    return AIServerPageContext(
        verified_route_name="injection-scheduling-v2",
        verified_path="/modules/production/injection-scheduling",
        verified_factory_id="huaxing",
        verified_module_id="injection-scheduling",
        knowledge_id="injection-scheduling",
        allowed_tool_groups=allowed_tool_groups,
    )


def tool_spec(
    executor: Callable[[object, FactoryArguments], object],
    *,
    serializer: Callable[[object], object] = lambda value: value,
    risk_level: AIToolRiskLevel = AIToolRiskLevel.READ_ONLY,
    max_result_rows: int = 50,
    timeout_seconds: float = 1,
) -> ToolSpec:
    return ToolSpec(
        name="scheduling.read",
        description="读取受限排产测试数据。",
        input_model=FactoryArguments,
        risk_level=risk_level,
        executor=executor,
        serializer=serializer,
        display_label="正在读取排产",
        tool_group="injection_scheduling",
        required_permission="injection_scheduling:read",
        allowed_departments=frozenset({"production"}),
        factory_argument="factory_id",
        requires_db=True,
        max_result_rows=max_result_rows,
        timeout_seconds=timeout_seconds,
    )


def call(name: str = "scheduling.read", arguments: str | None = None) -> ProviderToolCall:
    return ProviderToolCall(
        call_id="call-security",
        name=name,
        arguments_json=arguments or '{"factory_id":"huaxing"}',
    )


def execute_tool(
    executor: ToolExecutor,
    tool_call: ProviderToolCall,
    context: ToolExecutionContext,
):
    return asyncio.run(executor.execute(tool_call, context))


def test_unknown_url_near_name_and_arbitrary_fields_never_execute() -> None:
    executions: list[str] = []
    spec = tool_spec(lambda _context, _arguments: executions.append("executed"))
    executor = ToolExecutor(ToolRegistry((spec,)), settings())
    context = ToolExecutionContext(
        None,
        user_context(),
        "request-unknown",
        scheduling_page_context(),
    )

    outcomes = [
        execute_tool(executor, call("scheduling.rea"), context),
        execute_tool(executor, call("https://example.com/tool"), context),
        execute_tool(
            executor,
            call(arguments='{"factory_id":"huaxing","sql":"DROP TABLE x"}'),
            context,
        ),
    ]

    assert executions == []
    assert [item.error_code for item in outcomes] == [
        AIToolErrorCode.UNKNOWN_TOOL.value,
        AIToolErrorCode.UNKNOWN_TOOL.value,
        AIToolErrorCode.INVALID_ARGUMENTS.value,
    ]


def test_executor_rechecks_registered_tool_against_current_request_scope() -> None:
    executions: list[str] = []
    spec = tool_spec(
        lambda _context, _arguments: executions.append("executed") or {"ok": True}
    )
    executor = ToolExecutor(ToolRegistry((spec,)), settings())

    without_page = execute_tool(
        executor,
        call(),
        ToolExecutionContext(None, user_context(), "request-no-page"),
    )
    wrong_group = execute_tool(
        executor,
        call(),
        ToolExecutionContext(
            None,
            user_context(),
            "request-wrong-group",
            scheduling_page_context(allowed_tool_groups=("identity",)),
        ),
    )
    allowed = execute_tool(
        executor,
        call(),
        ToolExecutionContext(
            None,
            user_context(),
            "request-allowed",
            scheduling_page_context(),
        ),
    )

    assert without_page.error_code == AIToolErrorCode.UNKNOWN_TOOL.value
    assert wrong_group.error_code == AIToolErrorCode.UNKNOWN_TOOL.value
    assert allowed.ok
    assert executions == ["executed"]


@pytest.mark.parametrize(
    "arguments",
    [
        "{malformed",
        '{"factory_id":"not-a-factory"}',
        json.dumps({"factory_id": "huaxing", "note": "x" * 17}),
        json.dumps({"factory_id": "huaxing", "note": "x" * 20_000}),
    ],
)
def test_malformed_long_and_invalid_factory_arguments_are_rejected(
    arguments: str,
) -> None:
    executor = ToolExecutor(
        ToolRegistry((tool_spec(lambda _context, _arguments: {"ok": True}),)),
        settings(),
    )
    outcome = execute_tool(
        executor,
        call(arguments=arguments),
        ToolExecutionContext(
            None,
            user_context(),
            "request-invalid",
            scheduling_page_context(),
        ),
    )

    assert not outcome.ok
    assert outcome.error_code in {
        AIToolErrorCode.INVALID_ARGUMENTS.value,
        AIToolErrorCode.INVALID_FACTORY.value,
    }


def test_non_read_only_tools_are_hard_denied() -> None:
    executed = False

    def write_tool(_context: object, _arguments: FactoryArguments) -> dict[str, bool]:
        nonlocal executed
        executed = True
        return {"changed": True}

    executor = ToolExecutor(
        ToolRegistry(
            (
                tool_spec(
                    write_tool,
                    risk_level=AIToolRiskLevel.CONSEQUENTIAL_WRITE,
                ),
            )
        ),
        settings(),
    )
    outcome = execute_tool(
        executor,
        call(),
        ToolExecutionContext(None, user_context(), "request-write"),
    )

    assert not executed
    assert outcome.error_code == AIToolErrorCode.RISK_NOT_ALLOWED.value


def test_canonical_explicit_deny_and_cross_factory_are_rechecked() -> None:
    explicit_deny = AuthOverrideContext(
        id="deny-scheduling-read",
        permission_code="injection_scheduling:read",
        effect="deny",
        factory_id="huaxing",
        department="production",
    )
    audit_db = FakeAuditDb()
    executor = ToolExecutor(
        ToolRegistry((tool_spec(lambda _context, _arguments: {"ok": True}),)),
        settings(),
    )

    denied = execute_tool(
        executor,
        call(),
        ToolExecutionContext(
            audit_db,  # type: ignore[arg-type]
            user_context(overrides=(explicit_deny,)),
            "request-explicit-deny",
            scheduling_page_context(),
        ),
    )
    cross_factory = execute_tool(
        executor,
        call(arguments='{"factory_id":"huakang-b"}'),
        ToolExecutionContext(
            None,
            user_context(),
            "request-cross-factory",
            scheduling_page_context(),
        ),
    )

    assert denied.error_code == AIToolErrorCode.PERMISSION_DENIED.value
    assert cross_factory.error_code == AIToolErrorCode.INVALID_FACTORY.value
    assert audit_db.commits == 0
    assert audit_db.rollbacks == 0
    assert audit_db.records == []


def test_managed_postgres_session_sets_parameterized_transaction_timeout() -> None:
    session = PostgresManagedSession()

    def session_factory() -> PostgresManagedSession:
        session.lifecycle.append(("create", threading.get_ident()))
        return session

    def read_tool(context: ToolExecutionContext, _arguments: FactoryArguments):
        assert context.db is session
        session.lifecycle.append(("execute", threading.get_ident()))
        return {"ok": True}

    outcome = execute_tool(
        ToolExecutor(
            ToolRegistry((tool_spec(read_tool, timeout_seconds=2),)),
            settings(),
        ),
        call(),
        ToolExecutionContext(
            None,
            user_context(),
            "request-postgres-timeout",
            scheduling_page_context(),
            session_factory=session_factory,  # type: ignore[arg-type]
        ),
    )

    assert outcome.ok
    assert [event for event, _thread in session.lifecycle] == [
        "create",
        "statement_timeout",
        "execute",
        "rollback",
        "close",
    ]
    assert len({thread for _event, thread in session.lifecycle}) == 1
    assert len(session.statements) == 1
    statement, parameters = session.statements[0]
    assert "set_config('statement_timeout', :timeout_value, true)" in statement
    assert parameters == {"timeout_value": "1800ms"}


@pytest.mark.parametrize(
    ("sqlstate", "expected_error"),
    [
        ("57014", AIToolErrorCode.TIMEOUT),
        ("40001", AIToolErrorCode.EXECUTION_FAILED),
    ],
)
def test_managed_database_only_maps_query_cancellation_to_timeout(
    sqlstate: str,
    expected_error: AIToolErrorCode,
) -> None:
    session = ManagedSession()

    class DriverError(Exception):
        def __init__(self) -> None:
            super().__init__("private database detail must not escape")
            self.sqlstate = sqlstate

    def session_factory() -> ManagedSession:
        return session

    def failing_tool(_context: object, _arguments: FactoryArguments):
        raise OperationalError("private statement", {}, DriverError())

    outcome = execute_tool(
        ToolExecutor(
            ToolRegistry((tool_spec(failing_tool, timeout_seconds=1),)),
            settings(),
        ),
        call(),
        ToolExecutionContext(
            None,
            user_context(),
            "request-database-timeout-map",
            scheduling_page_context(),
            session_factory=session_factory,  # type: ignore[arg-type]
        ),
    )

    assert outcome.error_code == expected_error.value
    assert "private" not in outcome.provider_output_json
    assert session.rollbacks == 1
    assert session.closed == 1


def test_timeout_returns_then_managed_worker_eventually_closes_on_live_loop() -> None:
    started = threading.Event()
    release = threading.Event()
    closed = threading.Event()

    class BlockingSession(ManagedSession):
        def close(self) -> None:
            super().close()
            closed.set()

    session = BlockingSession()

    def session_factory() -> BlockingSession:
        session.lifecycle.append(("create", threading.get_ident()))
        return session

    def blocking_tool(_context: object, _arguments: FactoryArguments):
        started.set()
        release.wait(timeout=2)
        return {"ok": True}

    async def scenario() -> None:
        executor = ToolExecutor(
            ToolRegistry((tool_spec(blocking_tool, timeout_seconds=0.2),)),
            settings(),
        )
        task = asyncio.create_task(
            executor.execute(
                call(),
                ToolExecutionContext(
                    None,
                    user_context(),
                    "request-live-loop-timeout",
                    scheduling_page_context(),
                    session_factory=session_factory,  # type: ignore[arg-type]
                ),
            )
        )
        try:
            for _ in range(200):
                if started.is_set():
                    break
                await asyncio.sleep(0.005)
            assert started.is_set()
            outcome = await task
            assert outcome.error_code == AIToolErrorCode.TIMEOUT.value
            assert closed.is_set() is False

            release.set()
            for _ in range(200):
                if closed.is_set():
                    break
                await asyncio.sleep(0.005)
            assert closed.is_set() is True
        finally:
            release.set()
            if not task.done():
                await task

    asyncio.run(scenario())

    assert session.rollbacks == 1
    assert session.closed == 1


def test_managed_session_factory_owns_success_timeout_and_denial_lifecycles() -> None:
    created: list[ManagedSession] = []

    def session_factory() -> ManagedSession:
        session = ManagedSession()
        session.lifecycle.append(("create", threading.get_ident()))
        created.append(session)
        return session

    def read_tool(context: ToolExecutionContext, _arguments: FactoryArguments):
        assert context.db is created[-1]
        context.db.lifecycle.append(("execute", threading.get_ident()))  # type: ignore[attr-defined]
        return {"ok": True}

    success = execute_tool(
        ToolExecutor(ToolRegistry((tool_spec(read_tool),)), settings()),
        call(),
        ToolExecutionContext(
            None,
            user_context(),
            "request-managed-success",
            scheduling_page_context(),
            session_factory=session_factory,  # type: ignore[arg-type]
        ),
    )

    assert success.ok
    success_session = created[0]
    assert [event for event, _thread in success_session.lifecycle] == [
        "create",
        "execute",
        "rollback",
        "close",
    ]
    assert len({thread for _event, thread in success_session.lifecycle}) == 1

    def slow_tool(_context: object, _arguments: FactoryArguments):
        time.sleep(0.03)
        return {"ok": True}

    timeout = execute_tool(
        ToolExecutor(
            ToolRegistry((tool_spec(slow_tool, timeout_seconds=0.001),)),
            settings(),
        ),
        call(),
        ToolExecutionContext(
            None,
            user_context(),
            "request-managed-timeout",
            scheduling_page_context(),
            session_factory=session_factory,  # type: ignore[arg-type]
        ),
    )

    assert timeout.error_code == AIToolErrorCode.TIMEOUT.value
    timeout_session = created[1]
    assert timeout_session.rollbacks == 1
    assert timeout_session.closed == 1

    explicit_deny = AuthOverrideContext(
        id="deny-managed-audit",
        permission_code="injection_scheduling:read",
        effect="deny",
        factory_id="huaxing",
        department="production",
    )
    denial = execute_tool(
        ToolExecutor(
            ToolRegistry((tool_spec(lambda _context, _arguments: {"ok": True}),)),
            settings(),
        ),
        call(),
        ToolExecutionContext(
            None,
            user_context(overrides=(explicit_deny,)),
            "request-managed-denial",
            scheduling_page_context(),
            session_factory=session_factory,  # type: ignore[arg-type]
        ),
    )

    assert denial.error_code == AIToolErrorCode.PERMISSION_DENIED.value
    denial_session = created[2]
    assert denial_session.commits == 1
    assert denial_session.closed == 1
    assert len(denial_session.records) == 1
    assert "tool=scheduling.read" in denial_session.records[0].detail  # type: ignore[attr-defined]


def test_timeout_rows_bytes_fields_and_orm_results_fail_closed() -> None:
    async def slow_tool(_context: object, _arguments: FactoryArguments) -> object:
        await asyncio.sleep(0.05)
        return {"ok": True}

    cases = (
        (
            tool_spec(slow_tool, timeout_seconds=0.001),
            settings(),
            AIToolErrorCode.TIMEOUT,
        ),
        (
            tool_spec(lambda _context, _arguments: {"items": [1, 2, 3]}),
            settings(ai_max_tool_result_rows=2),
            AIToolErrorCode.RESULT_ROWS_EXCEEDED,
        ),
        (
            tool_spec(lambda _context, _arguments: {"text": "x" * 1_000}),
            settings(ai_max_tool_result_bytes=256),
            AIToolErrorCode.RESULT_BYTES_EXCEEDED,
        ),
        (
            tool_spec(lambda _context, _arguments: {"a": 1, "b": 2, "c": 3}),
            settings(ai_max_tool_result_fields=2),
            AIToolErrorCode.RESULT_FIELDS_EXCEEDED,
        ),
        (
            tool_spec(
                lambda _context, _arguments: AuthUser(
                    id="orm-user",
                    username="orm-user",
                )
            ),
            settings(),
            AIToolErrorCode.INVALID_RESULT,
        ),
    )

    for spec, configured_settings, expected_code in cases:
        outcome = execute_tool(
            ToolExecutor(ToolRegistry((spec,)), configured_settings),
            call(),
            ToolExecutionContext(
                None,
                user_context(),
                f"request-{expected_code.value}",
                scheduling_page_context(),
            ),
        )
        assert outcome.error_code == expected_code.value


def test_result_field_limit_measures_object_width_not_rows_times_columns() -> None:
    rows = [
        {f"field_{column}": f"row-{row}" for column in range(13)}
        for row in range(20)
    ]
    outcome = execute_tool(
        ToolExecutor(
            ToolRegistry(
                (tool_spec(lambda _context, _arguments: {"items": rows}),)
            ),
            settings(ai_max_tool_result_fields=64),
        ),
        call(),
        ToolExecutionContext(
            None,
            user_context(),
            "request-wide-page",
            scheduling_page_context(),
        ),
    )

    assert outcome.ok
    assert outcome.row_count == 20
    assert outcome.field_count == 13


def test_controlled_top_level_truncated_flag_reaches_execution_metadata() -> None:
    spec = tool_spec(
        lambda _context, _arguments: {
            "items": [{"id": "synthetic-row"}],
            "truncated": True,
        }
    )
    outcome = execute_tool(
        ToolExecutor(ToolRegistry((spec,)), settings()),
        call(),
        ToolExecutionContext(
            None,
            user_context(),
            "request-truncated-metadata",
            scheduling_page_context(),
        ),
    )

    assert outcome.ok
    assert outcome.truncated is True
    payload = json.loads(outcome.provider_output_json)
    assert payload["metadata"]["truncated"] is True


def test_identity_result_and_logs_exclude_sensitive_context_and_arguments(
    caplog: pytest.LogCaptureFixture,
) -> None:
    marker = "PROMPT_SECRET_MARKER"
    profile = AuthProfileContext(
        primary_factory_id="huaxing",
        primary_department="production",
        phone="13800000000",
        email="private@example.com",
    )
    context = ToolExecutionContext(
        None,
        user_context(profile=profile),
        "request-identity",
    )
    executor = ToolExecutor(build_default_tool_registry(), settings())

    with caplog.at_level(logging.INFO, logger="app.ai.tool"):
        outcome = execute_tool(
            executor,
            ProviderToolCall(
                call_id="call-identity",
                name="identity.get_current_context",
                arguments_json="{}",
            ),
            context,
        )

    assert outcome.ok
    assert "安全测试用户" in outcome.provider_output_json
    assert "华兴" in outcome.provider_output_json
    assert "private-username" not in outcome.provider_output_json
    assert "13800000000" not in outcome.provider_output_json
    assert "private@example.com" not in outcome.provider_output_json
    assert marker not in caplog.text
    assert "request_id=request-identity" in caplog.text
    assert "tool=identity.get_current_context" in caplog.text
