from datetime import datetime

from app.services import shipping_autogen, shipping_exports, shipping_loading


def test_so_exports_archive_into_monthly_and_daily_folders_with_filing_code(tmp_path, monkeypatch):
    monkeypatch.setattr(shipping_exports, 'EXPORT_ROOT', tmp_path)

    so_name = shipping_loading.sheet_code_filename(
        {'number': 'W1'},
        [{'filingCode': 'ROSS-279188253'}],
    )
    truck_name = shipping_autogen.filing_code_filename({}, [{'filingCode': 'GDSM-HKGM002686'}], '.xls')
    supp_name = shipping_autogen.filing_code_filename({}, [{'itemNo': 'BZ2001'}, {'itemNo': 'BZ2002'}], '.xlsx')
    assert so_name == 'ROSS-279188253.xls'
    assert truck_name == 'GDSM-HKGM002686.xls'
    assert supp_name == 'BZ2001_BZ2002.xlsx'

    p1 = shipping_exports.save_import_file('so_dk', so_name, b'day1', now=datetime(2026, 11, 1, 8, 30, 5))
    p2 = shipping_exports.save_import_file('so_zuru', 'ZURU01.xlsx', b'day24', now=datetime(2026, 11, 24, 9, 15, 0))
    p3 = shipping_exports.save_import_file('so_dk', 'DEC01.xls', b'dec', now=datetime(2026, 12, 3, 10, 0, 0))
    p_truck_day1 = shipping_exports.save_import_file('truck_bulk', 'TRUCK_A.xls', b't1', now=datetime(2026, 11, 1, 9, 0, 0))
    p_truck_day24 = shipping_exports.save_import_file('truck_export', truck_name, b't2', now=datetime(2026, 11, 24, 9, 15, 0))
    p_supp_day1 = shipping_exports.save_import_file('supplement', 'SUPP_A.xlsx', b'supp1', now=datetime(2026, 11, 1, 8, 0, 0))
    p_supp_day24 = shipping_exports.save_import_file('supplement', supp_name, b'supp2', now=datetime(2026, 11, 24, 9, 15, 0))
    p_customs = shipping_exports.save_import_file('customs', 'CUSTOMS.pdf', b'cust', now=datetime(2026, 11, 24, 9, 15, 0))

    assert p1 == str(tmp_path / 'SO 出货表' / '2026年11月' / 'ROSS-279188253.xls')
    assert p2 == str(tmp_path / 'SO 出货表' / '2026年11月' / 'ZURU01.xlsx')
    assert p3 == str(tmp_path / 'SO 出货表' / '2026年12月' / 'DEC01.xls')
    assert p_truck_day1 == str(tmp_path / '车的排出货表' / '2026年11月' / 'TRUCK_A.xls')
    assert p_truck_day24 == str(tmp_path / '车的排出货表' / '2026年11月' / 'GDSM-HKGM002686.xls')
    assert p_supp_day1 == str(tmp_path / '补料单' / '2026年11月' / 'SUPP_A.xlsx')
    assert p_supp_day24 == str(tmp_path / '补料单' / '2026年11月' / 'BZ2001_BZ2002.xlsx')
    assert p_customs == str(tmp_path / '通关一体化资料' / 'CUSTOMS.pdf')

    so_nov_files = sorted(f.name for f in (tmp_path / 'SO 出货表' / '2026年11月').iterdir())
    assert so_nov_files == ['ROSS-279188253.xls', 'ZURU01.xlsx']
    truck_nov_files = sorted(f.name for f in (tmp_path / '车的排出货表' / '2026年11月').iterdir())
    assert truck_nov_files == ['GDSM-HKGM002686.xls', 'TRUCK_A.xls']
    supp_nov_files = sorted(f.name for f in (tmp_path / '补料单' / '2026年11月').iterdir())
    assert supp_nov_files == ['BZ2001_BZ2002.xlsx', 'SUPP_A.xlsx']


def test_generated_doc_resolves_filing_code_from_order_ledger_when_lines_blank(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.models.customer_order_ledger import OrderLedgerLine
    from app.models.shipping_mail import ShippingGeneratedDoc, ShippingTask

    monkeypatch.setattr(shipping_exports, 'EXPORT_ROOT', tmp_path)
    engine = create_engine('sqlite:///:memory:')
    ShippingTask.__table__.create(engine)
    OrderLedgerLine.__table__.create(engine)
    ShippingGeneratedDoc.__table__.create(engine)

    with Session(engine) as db:
        db.add(ShippingTask(
            id='task-hk', factory_id='huaxing', mail_item_id='mail-hk', source_group_key='g1',
            source='mail', so_number='HKGM00268600', customer='', container_type='40HQ',
            port='盐田', destination_country='美国', shipment_mode='bulk', status='waiting',
            planned_ship_date='2026-07-15', si_deadline='', cutoff_date='2026-07-16T17:00',
            items_json='[]', warnings_json='[]', created_at='2026-11-24T09:00:00', updated_at='2026-11-24T09:00:00',
        ))
        db.add(OrderLedgerLine(
            id='ord-hk', factory_id='huaxing', customer_code='CENTURY', customer_name='CENTURY (CDS)',
            identity_key='k1', reference_no='HKGM00268600', product_no='GDSM-HKGM002686',
            quantity=None, shipped_quantity=0, status='active', version=1, revision=1,
            data={'contract_no': 'US2625089', 'po_no': 'PO-HKGM00268600'},
            created_at='2026-11-24T09:00:00', updated_at='2026-11-24T09:00:00',
        ))
        db.add(OrderLedgerLine(
            id='ord-bz1', factory_id='huaxing', customer_code='BZ', customer_name='BZ',
            identity_key='k2', reference_no='WKFSO202611', product_no='BZ2001',
            quantity=None, shipped_quantity=0, status='active', version=1, revision=1,
            data={'contract_no': 'CT-WKF-001', 'po_no': 'PO-BZ1'},
            created_at='2026-11-24T09:00:00', updated_at='2026-11-24T09:00:00',
        ))
        db.add(OrderLedgerLine(
            id='ord-bz2', factory_id='huaxing', customer_code='BZ', customer_name='BZ',
            identity_key='k3', reference_no='WKFSO202611', product_no='BZ2002',
            quantity=None, shipped_quantity=0, status='active', version=1, revision=1,
            data={'contract_no': 'CT-WKF-001', 'po_no': 'PO-BZ2'},
            created_at='2026-11-24T09:00:00', updated_at='2026-11-24T09:00:00',
        ))
        db.commit()

        truck_doc = ShippingGeneratedDoc(
            id='doc-truck', factory_id='huaxing', task_id='task-hk', module='truck_bulk',
            filename='车的排出货表_盐田散货_HKGM00268600.xlsx',
            header_json='{"tableName":"建联派运输，出盐田"}',
            lines_json='[{"so":"HKGM00268600","filingCode":""}]',
            created_at='2026-11-24T09:00:00', created_by='u1',
        )
        so_doc = ShippingGeneratedDoc(
            id='doc-so', factory_id='huaxing', task_id='task-hk', module='so_dk',
            filename='成隆达运输出盐田_HKGM00268600.xls',
            header_json='{"soNo":"HKGM00268600"}',
            lines_json='[]',
            created_at='2026-11-24T09:00:00', created_by='u1',
        )
        supp_doc = ShippingGeneratedDoc(
            id='doc-supp', factory_id='huaxing', task_id='task-bz', module='supplement',
            filename='补料单_WKFSO202611.xlsx',
            header_json='{"ref":"CT-WKF-001"}',
            lines_json='[{"salesConf":"CT-WKF-001","itemNo":""}]',
            created_at='2026-11-24T09:00:00', created_by='u1',
        )
        db.add_all([truck_doc, so_doc, supp_doc])
        db.commit()

        truck_name = shipping_autogen._resolved_doc_filename(
            truck_doc.module, truck_doc.filename, {'tableName': '建联派运输，出盐田'},
            [{'so': 'HKGM00268600', 'filingCode': ''}], db=db, factory_id='huaxing', task_id=truck_doc.task_id,
        )
        so_name = shipping_autogen._resolved_doc_filename(
            so_doc.module, so_doc.filename, {'soNo': 'HKGM00268600'}, [],
            db=db, factory_id='huaxing', task_id=so_doc.task_id,
        )
        supp_name = shipping_autogen._resolved_doc_filename(
            supp_doc.module, supp_doc.filename, {'ref': 'CT-WKF-001'},
            [{'salesConf': 'CT-WKF-001', 'itemNo': ''}], db=db, factory_id='huaxing', task_id=supp_doc.task_id,
        )

        assert truck_name == 'GDSM-HKGM002686.xlsx'
        assert so_name == 'GDSM-HKGM002686.xls'
        assert supp_name == 'BZ2001_BZ2002.xlsx'

        now = datetime(2026, 11, 24, 9, 50, 0)
        assert shipping_exports.save_import_file('truck_bulk', truck_name, b'x', now=now) == str(
            tmp_path / '车的排出货表' / '2026年11月' / 'GDSM-HKGM002686.xlsx'
        )
        assert shipping_exports.save_import_file('so_dk', so_name, b'x', now=now) == str(
            tmp_path / 'SO 出货表' / '2026年11月' / 'GDSM-HKGM002686.xls'
        )
        assert shipping_exports.save_import_file('supplement', supp_name, b'x', now=now) == str(
            tmp_path / '补料单' / '2026年11月' / 'BZ2001_BZ2002.xlsx'
        )
