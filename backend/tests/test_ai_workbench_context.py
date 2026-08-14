from app.services.ai.context_builder import build_server_page_context
from test_ai_conversation_context import _scheduling_context, _user


def test_workbench_continuation_rechecks_permission_for_bound_hint() -> None:
    context = _scheduling_context()
    authorized = build_server_page_context(context, _user())
    revoked = build_server_page_context(context, _user(permission=False))

    assert authorized is not None
    assert authorized.verified_factory_id == "huaxing"
    assert "injection_scheduling" in authorized.allowed_tool_groups
    assert revoked is not None
    assert revoked.verified_factory_id is None
    assert "injection_scheduling" not in revoked.allowed_tool_groups
