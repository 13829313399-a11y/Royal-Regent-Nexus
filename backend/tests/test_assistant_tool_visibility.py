"""Native tool-schema authority is separate from invocation/source authorization."""
from dataclasses import replace
import pytest
from sqlalchemy.exc import OperationalError
from test_assistant_api import env
from test_work_center_api import actor
from test_internal_quote_queries import capture,no_writes


def names(tools):
    return {tool['function']['name'] for tool in tools}


def test_native_factory_permission_and_revocation_filter_tools_without_sql_writes(env):
    from app.services.assistant import business
    _,dbm,_,_=env
    user=actor('alice',factory='huakang-a',department='sales-business',permissions=('customer_order:read',))
    statements,stop=capture(dbm)
    try:
        expected={'get_my_work','list_customer_orders'}
        assert names(business.permitted_tools(user,'huakang-a'))==expected
        assert names(business.permitted_tools(user,'huakang-b'))=={'get_my_work'}
        assert names(business.permitted_tools(user,'not-a-factory'))==set()
        assert names(business.permitted_tools(user,'authorized'))==expected
        revoked=replace(user,permissions=frozenset(),grants=())
        assert names(business.permitted_tools(revoked,'huakang-a'))=={'get_my_work'}
        assert business.permitted_tools(None,'huakang-a')==[]
    finally:stop()
    no_writes(statements)


def test_order_surface_remains_available_without_independent_inventory_permission(env):
    from app.services.assistant import business,cartons
    from app.services.assistant.errors import AssistantError
    _,dbm,_,_=env
    user=actor('alice',factory='huakang-a',department='pmc-warehouse',permissions=('carton_procurement:order_write',))
    with dbm.SessionLocal() as db:
        cartons.authorize(db,user,'huakang-a',view='orders')
        with pytest.raises(AssistantError):cartons.authorize(db,user,'huakang-a',view='inventory')
    assert cartons.NAME in names(business.permitted_tools(user,'huakang-a'))


def test_one_unavailable_domain_does_not_advertise_it_or_hide_other_native_tools(env):
    from app.services.assistant import business
    _,_,_,patch=env
    user=actor('alice',factory='huakang-a',department='sales-business',permissions=('customer_order:read',))
    baseline=names(business.permitted_tools(user,'huakang-a'))
    assert 'list_customer_orders' in baseline
    original=business.authorize
    def outage(db,user,name,factory):
        if name=='list_customer_orders':raise OperationalError('SELECT private credentials',{},Exception('PRIVATE-SQL'))
        return original(db,user,name,factory)
    patch.setattr(business,'authorize',outage)
    tools=business.permitted_tools(user,'huakang-a')
    assert names(tools)==baseline-{'list_customer_orders'}
    assert 'PRIVATE-SQL' not in str(tools) and 'private credentials' not in str(tools)
