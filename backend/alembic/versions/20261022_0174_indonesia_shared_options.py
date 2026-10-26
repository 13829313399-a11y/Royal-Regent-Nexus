"""One shared Indonesia option library; preserve every factory record and receipt."""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from uuid import NAMESPACE_URL, uuid5
from alembic import op
import sqlalchemy as sa

revision = '20261022_0174'
down_revision = '20261022_0173'
branch_labels = None
depends_on = None
FACTORIES = {'huaxing', 'huadeng', 'huakang-a', 'huakang-b', 'huakang-c', 'huakang-d'}
SUPPLIERS = ['华兴玩具制品（河源）有限公司', '华登玩具制品（河源）有限公司', '华康玩具制品（河源）有限公司', '深圳市伟利橡塑制品有限公司', '伯爵印刷（河源）有限公司', '新利達環球發展有限公司', '东莞市星徽纸品有限公司', '香港睿同科技有限公司']
CHOICES = {'category': ['彩盒/彩卡', '利宝说明书', '塑胶', '半成品', '电池'], 'customs_unit': ['KGM', 'TNE', 'PCE'],
           'unit': ['pcs'], 'usage': ['产品配件'], 'currency': ['USD', 'HKD'], 'supplier': SUPPLIERS,
           'export_company': SUPPLIERS[:3] + ['新利達環球發展有限公司', '深圳市华胜益出口贸易有限公司']}


def key(group, value):
    return hashlib.sha256(json.dumps([group, value.strip().casefold()], ensure_ascii=False).encode()).hexdigest()


def plan(bind):
    result = {}
    for group, values in CHOICES.items():
        for value in values:
            data = dict(group=group, value=value, status='active', billing_basis='weight' if group == 'customs_unit' and value in {'KGM', 'TNE'} else 'quantity', kg_per_unit='1000' if group == 'customs_unit' and value == 'TNE' else '1')
            result[key(group, value)] = data
    legacy = sa.table('indonesia_material_options', sa.column('id'), sa.column('factory_id'), sa.column('version'), sa.column('data', sa.JSON))
    grouped = {}
    for row in bind.execute(sa.select(legacy)).mappings():
        data = dict(row['data'])
        if row['factory_id'] not in FACTORIES or data.get('group') not in CHOICES or not str(data.get('value', '')).strip():
            raise RuntimeError('旧基础选项身份无效，请先核对；未执行共用迁移')
        data['value'] = data['value'].strip().upper() if data['group'] in {'currency', 'customs_unit'} else data['value'].strip()
        if data['group'] == 'unit':
            data['value'] = data['value'].casefold()
        if data['group'] != 'customs_unit':
            data.update(billing_basis='quantity', kg_per_unit='1')
        grouped.setdefault(key(data['group'], data['value']), []).append((row, data))
    for identity, entries in grouped.items():
        first = entries[0][1]
        signature = lambda data: (data['status'], bool(data.get('deleted')), data['billing_basis'], Decimal(data['kg_per_unit']))
        default = result.get(identity)
        if any(signature(data) != signature(first) for _, data in entries) or (
            {row['factory_id'] for row, _ in entries} != FACTORIES and (
                first['status'] != 'active' or first.get('deleted') or (default is not None and signature(default) != signature(first)))):
            raise RuntimeError(f"共用选项存在启停、删除或换算冲突：{first['group']} / {first['value']}；请人工确认后再迁移")
        data = {name: first[name] for name in ('group', 'value', 'status', 'billing_basis', 'kg_per_unit')}
        if first.get('deleted'):
            data.update(deleted=True, deleted_by=first.get('deleted_by'), deleted_at=first.get('deleted_at'))
        data['legacy_sources'] = [dict(id=row['id'], factory_id=row['factory_id'], version=row['version']) for row, _ in entries]
        result[identity] = data
    return result


def upgrade():
    if op.get_context().as_sql:
        raise RuntimeError('共用基础选项迁移需在线核对原数据，不支持离线 SQL')
    bind = op.get_bind()
    merged = plan(bind)  # Fail before DDL on ambiguity.
    with bind.begin_nested():
        table = op.create_table('indonesia_material_shared_options',
            sa.Column('id', sa.String(64), primary_key=True), sa.Column('business_key', sa.String(64), nullable=False),
            sa.Column('version', sa.Integer, nullable=False), sa.Column('data', sa.JSON, nullable=False),
            sa.Column('updated_at', sa.String(40), nullable=False), sa.UniqueConstraint('business_key'), sa.CheckConstraint('version > 0'))
        now = datetime.now(timezone.utc).isoformat(timespec='seconds')
        bind.execute(table.insert(), [dict(id=str(uuid5(NAMESPACE_URL, 'indonesia-shared-options:' + identity)), business_key=identity,
                                          version=1, data=data, updated_at=now) for identity, data in merged.items()])


def validate_shared_options_schema(bind):
    inspector = sa.inspect(bind)
    table = 'indonesia_material_shared_options'
    if not inspector.has_table(table):
        raise RuntimeError('缺少全厂共用基础选项表')
    columns = {c['name']: c for c in inspector.get_columns(table)}
    names = {'id', 'business_key', 'version', 'data', 'updated_at'}
    unique = {frozenset(item['column_names']) for item in inspector.get_unique_constraints(table)}
    if (not names <= columns.keys() or any(columns[name]['nullable'] for name in names)
            or inspector.get_pk_constraint(table)['constrained_columns'] != ['id']
            or frozenset({'business_key'}) not in unique):
        raise RuntimeError('共用基础选项表结构不完整')


def downgrade():
    raise RuntimeError('共用基础选项已合并，拒绝降级丢失维护记录；请使用前向迁移')
