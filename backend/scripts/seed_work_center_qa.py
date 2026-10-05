"""Create a NEW isolated fixture database for browser acceptance; never reuse real data."""
import argparse
import json
import os
import sys
from pathlib import Path

def main():
    p = argparse.ArgumentParser(); p.add_argument('--database', type=Path, required=True); args = p.parse_args()
    if args.database.exists(): p.error('Refusing existing database')
    args.database.parent.mkdir(parents=True, exist_ok=True)
    os.environ['DATABASE_URL'] = 'sqlite:///' + args.database.as_posix()
    os.environ['SEED_ADMIN_PASSWORD'] = 'WorkCenterQa123!'
    os.environ['SPRAY_OPS_ENABLED'] = 'false'; os.environ['UV_OPS_ENABLED'] = 'false'
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.db import init_db, SessionLocal
    init_db()
    from app.models.auth import AuthUserRole, SystemNotification, AuthRegistrationRequest
    from app.models.molding_sample import MoldingSampleOrder, MoldingSampleAuditLog
    from app.models.internal_quote import InternalQuote, InternalQuoteSection
    from app.services.work_center.reconciliation import reconcile
    with SessionLocal() as db:
        for role, factory, department in [('engineering_supervisor', 'huakang-c', 'engineering'), ('molding_clerk', 'huakang-a', 'molding'), ('engineer', 'huaxing', 'engineering')]:
            db.add(AuthUserRole(id=f'qa-{role}', user_id='user-admin', role_id=role, factory_id=factory, department=department))
        for i in range(5):
            db.add(MoldingSampleOrder(id=f'qa-mold-{i}', factory_id='huakang-c', production_factory_id='huakang-a',
                order_number=f'C-PB-260928-{i+1:03}', product_name=['仿真动物系列 · 熊猫头部组件', '儿童厨房套装 · 注塑外壳', '海洋探索系列 · 鲸鱼尾鳍', '森林伙伴 · 可动关节组件', '太空探险 · 头盔透明件'][i],
                date='2026-09-28', status='待审核' if i < 2 else '待生产' if i < 4 else '生产中', created_at=f'2026-09-2{i+3} 09:00:00'))
        for i in range(4):
            db.add(AuthRegistrationRequest(id=f'qa-register-{i}', user_id='user-admin', username=f'qa-pending-{i}', display_name='隔离测试申请',
                factory_id='huakang-a', department='engineering', submitted_at=f'2026-09-2{i+5} 10:00:00'))
        for i in range(3):
            q = InternalQuote(id=f'qa-quote-{i}', factory_id='huaxing', workshop_code='A', workshop_name='A车间', quote_no=f'RR-260928-{i+1:03}',
                product_name=['欢乐农场互动套装', '城市消防救援系列', '复古迷你厨房'][i], customer='合成客户', qty=24000, version_label='V1',
                status='filling', module_version='v3', created_by='user-admin', created_by_name='测试', created_at='2026-09-25 14:30:00', updated_at='2026-09-28 10:00:00',
                target_date='2026-09-27' if i == 0 else '2026-09-29')
            db.add(q); db.flush()
            db.add(InternalQuoteSection(id=f'qa-section-{i}', quote_id=q.id, department='engineering', department_name='工程', status='draft', is_required=True))
        db.add(SystemNotification(id='qa-identity', type='identity_changed', target_user_id='user-admin', title='任职信息更新', created_at='2026-09-28 11:20:00'))
        db.commit()
        report = reconcile(db, apply=True); db.commit()
        print(json.dumps(report, ensure_ascii=False))

if __name__ == '__main__': main()
