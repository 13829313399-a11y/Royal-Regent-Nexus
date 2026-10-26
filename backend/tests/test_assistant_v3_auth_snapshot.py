"""Cross-process evidence continuity and fail-closed authorization changes."""
from dataclasses import replace
import os
from pathlib import Path
import subprocess
import sys

import pytest
from test_assistant_api import env
from test_work_center_api import actor


def test_fingerprint_is_identical_across_python_hash_seeds():
    script = """
from app.services.auth import AuthContext, AuthGrantContext
from app.services.assistant.auth_snapshot import digest
p=frozenset(['injection_scheduling:read','three_d_printing:read','customer_order:read','internal_quote:read'])
g=AuthGrantContext(role_id='test',role_name='test',factory_id='huakang-a',department='production',permissions=p,read_permissions=p)
u=AuthContext(id='test',username='test',display_name='test',roles=('test',),role_codes=('test',),permissions=p,factory_scopes=('huakang-a',),department_scopes=('production',),grants=(g,))
print(digest(u,1,'enforce'))
"""
    values = []
    for seed in ("11", "29", "131"):
        environment = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(Path(__file__).parents[1])}
        result = subprocess.run([sys.executable, "-c", script], env=environment, capture_output=True, text=True, timeout=30, check=True)
        values.append(result.stdout.strip())
    assert len(set(values)) == 1 and values[0].startswith("auth3:")


@pytest.mark.parametrize("change", ["grant", "override", "catalog", "revision", "identity", "epoch", "mode", "account", "scope"])
def test_permission_boundary_changes_invalidate_snapshot(change):
    from app.services.assistant.auth_snapshot import digest
    from app.services.auth import AuthOverrideContext
    user = actor("alice", department="production", permissions=("injection_scheduling:read",))
    before = digest(user, 1, "enforce")
    epoch, mode = 1, "enforce"
    if change == "grant": user = replace(user, grants=(replace(user.grants[0], factory_ceiling=("huaxing",)),))
    if change == "override": user = replace(user, overrides=(AuthOverrideContext("deny", "injection_scheduling:read", "deny", "huakang-a", "production"),))
    if change == "catalog": user = replace(user, active_permission_codes=frozenset(), permission_catalog_loaded=True)
    if change == "revision": user = replace(user, authorization_version=2)
    if change == "identity": user = replace(user, identity={**user.identity, "effective_context_key": "changed"})
    if change == "epoch": epoch = 2
    if change == "mode": mode = "legacy"
    if change == "account": user = replace(user, account_available=False)
    if change == "scope": user = replace(user, factory_scopes=("huaxing",))
    assert digest(user, epoch, mode) != before


def test_business_history_checks_new_and_legacy_snapshots_without_relaxing_visibility(env):
    from app.services.assistant import business, visibility
    from app.services.work_center.service import context
    client, dbm, _, _ = env
    user = actor("alice", department="production", permissions=("injection_scheduling:read",))
    _, source, _ = business.query(user, "get_injection_overview", {"factory_id": "huakang-a"}, "test-run")
    assert source["authorization_fingerprint"].startswith("auth3:")
    assert visibility.allowed(user, [source])
    with dbm.SessionLocal() as db:
        legacy = {**source, "authorization_fingerprint": context(db, user)[1]}
    assert visibility.allowed(user, [legacy])
    assert not visibility.allowed(user, [{**legacy, "authorization_fingerprint": "0"*32}])
    assert not visibility.allowed(user, [{**source, "authorization_fingerprint": "future:unknown"}])
    assert not visibility.allowed(replace(user, authorization_version=1), [source])
    denied = replace(user, grants=(), permissions=frozenset())
    assert not visibility.allowed(denied, [source])
    assert not visibility.allowed(denied, [legacy])
