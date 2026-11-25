import io
import json

from fastapi import HTTPException
import openpyxl
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.customer_order_ledger import OrderLedgerLine
from app.models.shipping_mail import (
    ShippingGeneratedDoc,
    ShippingLoadingSheet,
    ShippingPalletExclusion,
    ShippingPalletOverride,
    ShippingPalletRecord,
    ShippingTask,
)
from app.services.auth import AuthContext, AuthGrantContext
from app.services import shipping_pallets


def _user(*factories: str, superadmin: bool = False, can_write: bool = True) -> AuthContext:
    perms = {'shipping:read'}
    if can_write:
        perms.add('shipping:write')
    if superadmin:
        grants = (
            AuthGrantContext(
                role_id='admin',
                role_name='管理员',
                factory_id='*',
                department='*',
                permissions=frozenset(perms),
                role_code='admin',
            ),
        )
    else:
        grants = tuple(
            AuthGrantContext(
                role_id='shipping',
                role_name='船务',
                factory_id=fid,
                department='*',
                permissions=frozenset(perms),
            )
            for fid in factories
        )
    return AuthContext(
        id='u-1',
        username='tester',
        display_name='测试员',
        roles=('shipping',),
        role_codes=('shipping',),
        permissions=frozenset(perms),
        factory_scopes=factories,
        department_scopes=('*',),
        grants=grants,
    )


def _seed_db(db: Session) -> None:
    db.add(ShippingLoadingSheet(
        id='load-ross',
        factory_id='huaxing',
        number='W1',
        sheet_date='2026-11-23',
        task_id='task-ross',
        header_json=json.dumps({
            'soNo': '279188253',
            'contractNo': '298379137',
            'containerNo': 'MSKU111',
            'containerType': '40GP',
            'brandNote': 'ROSS',
        }),
        lines_json=json.dumps([{'filingCode': 'ROSS-279188253', 'cartons': 100, 'pallet': 4}]),
        totals_json='{}',
        created_by='u-1',
        created_at='2026-11-23T10:00:00',
    ))
    db.add(ShippingGeneratedDoc(
        id='supp-ross',
        factory_id='huaxing',
        task_id='task-ross',
        module='supplement',
        filename='ROSS-279188253.xlsx',
        header_json=json.dumps({'customerMarket': 'ROSS', 'date': '2026-11-23'}),
        lines_json=json.dumps([{'itemNo': 'ROSS-279188253', 'pallet': '6', 'ctns': 100, 'containerNo': 'MSKU111'}]),
        created_at='2026-11-23T11:00:00',
        created_by='u-1',
    ))
    db.add(ShippingGeneratedDoc(
        id='truck-gdsm',
        factory_id='huaxing',
        task_id='task-gdsm',
        module='truck_export',
        filename='GDSM-HKGM002686.xls',
        header_json=json.dumps({
            'brandName': 'CENTURY',
            'sheetDate': '2026-11-24',
            'bookingNo': 'HKGM00268600',
            'contractNo': 'US2625089',
            'vehicle': 'W218',
            'truckType': '3T',
        }),
        lines_json=json.dumps([{'filingCode': 'GDSM-HKGM002686', 'cartons': 40, 'boards': '5'}]),
        created_at='2026-11-24T09:00:00',
        created_by='u-1',
    ))
    db.add(ShippingLoadingSheet(
        id='load-huadeng',
        factory_id='huadeng',
        number='W2',
        sheet_date='2026-11-24',
        task_id='task-hd',
        header_json=json.dumps({
            'soNo': 'HD202611',
            'contractNo': 'CT-HD-01',
            'containerNo': 'HMMU222',
            'containerType': '40HQ',
            'brandNote': 'SIMBA',
        }),
        lines_json=json.dumps([{'filingCode': 'HD-001', 'cartons': 80, 'pallet': 8}]),
        totals_json='{}',
        created_by='u-1',
        created_at='2026-11-24T10:00:00',
    ))
    db.add(ShippingLoadingSheet(
        id='load-oct',
        factory_id='huaxing',
        number='W9',
        sheet_date='2026-10-15',
        task_id='task-oct',
        header_json=json.dumps({'soNo': 'OCT01', 'containerNo': 'OCTU999', 'containerType': '40HQ', 'brandNote': 'OCT'}),
        lines_json=json.dumps([{'filingCode': 'OCT-1', 'cartons': 10, 'pallet': 3}]),
        totals_json='{}',
        created_by='u-1',
        created_at='2026-10-15T10:00:00',
    ))
    db.commit()


def _create_memory_db() -> Session:
    engine = create_engine('sqlite:///:memory:')
    ShippingTask.__table__.create(engine)
    OrderLedgerLine.__table__.create(engine)
    ShippingLoadingSheet.__table__.create(engine)
    ShippingGeneratedDoc.__table__.create(engine)
    ShippingPalletRecord.__table__.create(engine)
    ShippingPalletExclusion.__table__.create(engine)
    ShippingPalletOverride.__table__.create(engine)
    return Session(engine)


def test_pallet_stats_aggregates_dedups_and_enforces_factory_scope():
    with _create_memory_db() as db:
        _seed_db(db)
        admin = _user(superadmin=True)

        all_nov = shipping_pallets.build_pallet_stats(db, admin, factory_id='all', month='2026-11')
        assert all_nov['summary']['totalPallets'] == 19
        assert all_nov['summary']['totalContainers'] == 2
        assert all_nov['summary']['estimatedCost'] == 1245.0
        assert len(all_nov['groups']) == 3
        assert len(all_nov['details']) == 3

        ross_custom = shipping_pallets.build_pallet_stats(
            db, admin, factory_id='huaxing', month='2026-11', customer='ROSS', unit_price=80.0,
        )
        assert ross_custom['summary']['totalPallets'] == 6
        assert ross_custom['summary']['totalContainers'] == 1
        assert ross_custom['summary']['estimatedCost'] == 480.0
        assert ross_custom['details'][0]['source'] == '柜货单 / 补料单'

        hx_only = _user('huaxing')
        scoped = shipping_pallets.build_pallet_stats(db, hx_only, factory_id='all', month='2026-11')
        assert [f['id'] for f in scoped['availableFactories']] == ['huaxing']
        assert scoped['summary']['totalPallets'] == 11
        with pytest.raises(HTTPException) as exc:
            shipping_pallets.build_pallet_stats(db, hx_only, factory_id='huadeng', month='2026-11')
        assert exc.value.status_code == 403


def test_manual_pallet_crud_multi_year_retention_and_search():
    with _create_memory_db() as db:
        _seed_db(db)
        admin = _user(superadmin=True)

        rec_2025 = shipping_pallets.create_manual_pallet_record(db, admin, {
            'factory_id': 'huaxing',
            'ship_date': '2025-08-12',
            'customer': 'ZURU',
            'container_no': 'ZURU202501',
            'container_type': '40HQ',
            'so_no': 'SO2025',
            'contract_no': 'CT2025',
            'filing_codes': 'ZU-01, ZU-02',
            'spec': '标准木卡板 (1200×1000)',
            'cartons': 120,
            'pallets': 12,
            'unit_price': 70,
            'is_container': True,
            'remark': '2025归档补录',
        })
        assert rec_2025['shipDate'] == '2025-08-12'

        shipping_pallets.create_manual_pallet_record(db, admin, {
            'factory_id': 'huaxing',
            'ship_date': '2026-11-25',
            'customer': 'MOOSE',
            'container_no': 'MOOSE888',
            'pallets': 4,
            'unit_price': 65,
            'remark': '加急出货',
        })

        stats_2025 = shipping_pallets.build_pallet_stats(db, admin, factory_id='huaxing', year='2025', month='all')
        assert '2025' in stats_2025['availableYears']
        assert '2026' in stats_2025['availableYears']
        assert stats_2025['summary']['totalPallets'] == 12
        assert stats_2025['summary']['totalContainers'] == 1
        assert stats_2025['summary']['estimatedCost'] == 840.0
        assert stats_2025['details'][0]['editable'] is True
        assert stats_2025['details'][0]['remark'] == '2025归档补录'

        shipping_pallets.update_manual_pallet_record(db, admin, rec_2025['id'], {
            'factory_id': 'huaxing',
            'ship_date': '2025-08-12',
            'customer': 'ZURU',
            'container_no': 'ZURU202501',
            'pallets': 15,
            'unit_price': 70,
            'remark': '加厚卡板',
        })

        all_years_search = shipping_pallets.build_pallet_stats(
            db, admin, factory_id='huaxing', year='all', month='all', q='ZURU2025',
        )
        assert all_years_search['summary']['totalPallets'] == 15
        assert all_years_search['summary']['recordCount'] == 1
        assert all_years_search['details'][0]['remark'] == '加厚卡板'

        filename, xlsx_bytes = shipping_pallets.export_pallet_reconciliation_xlsx(
            db, admin, factory_id='huaxing', year='2026', month='all',
        )
        assert filename == '卡板年度对账_2026全年.xlsx'
        wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=True)
        ws2 = wb['柜号明细']
        assert ws2.cell(1, 15).value == '备注'
        assert any(ws2.cell(r, 15).value == '加急出货' for r in range(2, ws2.max_row))


def test_batch_delete_manual_and_synced_exclusion_and_restore():
    with _create_memory_db() as db:
        _seed_db(db)
        admin = _user(superadmin=True)

        manual = shipping_pallets.create_manual_pallet_record(db, admin, {
            'factory_id': 'huaxing',
            'ship_date': '2026-11-26',
            'customer': 'PLAYMATE',
            'pallets': 3,
            'unit_price': 65,
        })

        res = shipping_pallets.batch_delete_pallet_records(db, admin, [
            {'id': manual['id'], 'factoryId': 'huaxing', 'recordType': 'manual'},
            {'id': 'load-ross', 'factoryId': 'huaxing', 'recordType': 'loading_sheet'},
        ])
        assert res == {'deletedManualCount': 1, 'excludedSyncCount': 1, 'totalRemoved': 2}

        assert db.get(ShippingPalletRecord, manual['id']) is None
        # Original loading sheet stays untouched while both load-ross and paired supp-ross stay hidden
        assert db.get(ShippingLoadingSheet, 'load-ross') is not None

        after_delete = shipping_pallets.build_pallet_stats(db, admin, factory_id='huaxing', month='2026-11')
        assert after_delete['excludedCount'] == 1
        assert [d['customer'] for d in after_delete['details']] == ['CENTURY']

        restored = shipping_pallets.restore_excluded_pallet_records(db, admin, 'huaxing')
        assert restored == {'restoredCount': 1}
        after_restore = shipping_pallets.build_pallet_stats(db, admin, factory_id='huaxing', month='2026-11')
        assert after_restore['excludedCount'] == 0
        assert sorted(d['customer'] for d in after_restore['details']) == ['CENTURY', 'ROSS']


def test_pallet_mutation_enforces_write_permission_and_factory_scope():
    with _create_memory_db() as db:
        _seed_db(db)
        readonly = _user('huaxing', can_write=False)
        with pytest.raises(HTTPException) as exc1:
            shipping_pallets.create_manual_pallet_record(db, readonly, {
                'factory_id': 'huaxing',
                'ship_date': '2026-11-24',
                'customer': 'ROSS',
                'pallets': 2,
            })
        assert exc1.value.status_code == 403

        hx_writer = _user('huaxing', can_write=True)
        with pytest.raises(HTTPException) as exc2:
            shipping_pallets.batch_delete_pallet_records(db, hx_writer, [
                {'id': 'load-huadeng', 'factoryId': 'huadeng', 'recordType': 'loading_sheet'},
            ])
        assert exc2.value.status_code == 403


def test_pallet_reconciliation_export_returns_two_sheet_xlsx():
    with _create_memory_db() as db:
        _seed_db(db)
        admin = _user(superadmin=True)
        filename, content = shipping_pallets.export_pallet_reconciliation_xlsx(
            db, admin, factory_id='all', month='2026-11',
        )
        assert filename == '卡板月度对账_2026-11.xlsx'
        assert content[:2] == b'PK'

        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        assert wb.sheetnames == ['月度汇总', '柜号明细']
        ws1 = wb['月度汇总']
        ws2 = wb['柜号明细']
        assert ws1.cell(ws1.max_row, 1).value == '合计'
        assert ws1.cell(ws1.max_row, 4).value == 2
        assert ws1.cell(ws1.max_row, 5).value == 19
        assert ws1.cell(ws1.max_row, 7).value == 1245.0
        assert ws2.cell(ws2.max_row, 1).value == '合计'
        assert ws2.cell(ws2.max_row, 11).value == 19


def test_summary_group_edit_and_synced_row_override_persist_across_queries():
    with _create_memory_db() as db:
        _seed_db(db)
        admin = _user(superadmin=True)

        # Edit synced ROSS summary row directly (change customer, factory, spec, container_count, pallets, unit_price, custom cost)
        res = shipping_pallets.update_pallet_group(db, admin, {
            'items': [{'id': 'load-ross', 'factoryId': 'huaxing', 'originFactoryId': 'huaxing', 'recordType': 'loading_sheet'}],
            'factory_id': 'huadeng',
            'customer': 'ROSS-VIP',
            'spec': '加厚出口卡板 (1200×1200)',
            'container_count': 3,
            'total_pallets': 20,
            'unit_price': 80,
            'estimated_cost': 1550,
            'cost_overridden': True,
        })
        assert res == {'updatedCount': 1}

        # Original synced sheet keeps original factory_id and raw payload untouched
        orig_sheet = db.get(ShippingLoadingSheet, 'load-ross')
        assert orig_sheet is not None
        assert orig_sheet.factory_id == 'huaxing'

        # Querying destination factory shows the edited summary row & overridden KPIs
        hd_stats = shipping_pallets.build_pallet_stats(db, admin, factory_id='huadeng', month='2026-11')
        vip_group = next(g for g in hd_stats['groups'] if g['customer'] == 'ROSS-VIP')
        assert vip_group['factoryName'] == '华登'
        assert vip_group['spec'] == '加厚出口卡板 (1200×1200)'
        assert vip_group['containerCount'] == 3
        assert vip_group['totalPallets'] == 20
        assert vip_group['unitPrice'] == 80.0
        assert vip_group['estimatedCost'] == 1550.0
        # 8 (SIMBA load-huadeng) + 20 (moved ROSS-VIP) = 28 pallets; 1 + 3 = 4 containers
        assert hd_stats['summary']['totalPallets'] == 28
        assert hd_stats['summary']['totalContainers'] == 4

        # Source factory huaxing no longer counts load-ross under old customer
        hx_stats = shipping_pallets.build_pallet_stats(db, admin, factory_id='huaxing', month='2026-11')
        assert all(g['customer'] != 'ROSS' for g in hx_stats['groups'])

        # Single synced row update via dialog resets custom group cost override & recalculates
        updated = shipping_pallets.update_manual_pallet_record(db, admin, 'load-ross', {
            'record_type': 'loading_sheet',
            'origin_factory_id': 'huaxing',
            'factory_id': 'huaxing',
            'ship_date': '2026-11-23',
            'customer': 'ROSS-FIXED',
            'pallets': 9,
            'unit_price': 70,
            'spec': '标准木卡板 (1200×1000)',
            'remark': '明细调整',
        })
        assert updated['customer'] == 'ROSS-FIXED'
        hx_after = shipping_pallets.build_pallet_stats(db, admin, factory_id='huaxing', month='2026-11', customer='ROSS-FIXED')
        assert hx_after['summary']['totalPallets'] == 9
        assert hx_after['summary']['estimatedCost'] == 630.0
        assert hx_after['details'][0]['remark'] == '明细调整'

        # Cross-factory move enforces write permission on both origin and target factories
        hx_only = _user('huaxing', can_write=True)
        with pytest.raises(HTTPException) as exc:
            shipping_pallets.update_pallet_group(db, hx_only, {
                'items': [{'id': 'truck-gdsm', 'factoryId': 'huaxing', 'recordType': 'generated_doc'}],
                'factory_id': 'huadeng',
                'customer': 'CENTURY',
                'spec': '标准木卡板 (1200×1000)',
                'container_count': 1,
                'total_pallets': 5,
                'unit_price': 65,
            })
        assert exc.value.status_code == 403
