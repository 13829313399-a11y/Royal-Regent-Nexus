"""One contract/authority resolver. Metadata-only aliases; no copied legacy facts.

All persisted mutations are called after the existing IAM -> factory lock. Reads
never create a root, binding, folder, or compatibility event. Row-status reads
prefetch exact keys; only cold contract discovery queries legacy metadata.
"""
import copy
from collections.abc import Mapping

from fastapi import HTTPException
from sqlalchemy import JSON, cast, func, select, text

from app.models.carton_procurement import CartonAuditEvent, CartonCustomer, CartonOrder
from app.services.carton_mark_assets import identity

# Reuse the existing PRIVATE metadata entity excluded by generic audit routes.
# Prefixes CMF2 / CMT / CMR separate roots, bindings and operation receipts.
# Adding public entity types here would expose aliases through legacy audit APIs.
CONTRACTS = 'carton_material_request'
BINDINGS = 'carton_material_request'


def service():
    from app.services import carton_materials
    return carton_materials


def contract_id(factory, customer_id, contract):
    if not identity(contract):
        raise HTTPException(422, '请填写合同号；本期不支持无合同资料')
    return 'CMF2-' + service().digest([factory, customer_id, identity(contract)])


def context_id(root, data):
    return 'CMO-' + service().digest([root, identity(data.get('item_no') or ''), identity(data.get('po') or '')])


def target_key(factory, target):
    return 'CMT-' + service().digest([factory, target.kind, target.id, target.sheet, target.row])


def signature(data):
    return [identity(str(data.get(key) or '')) for key in ('customer_code', 'contract_no', 'item_no', 'po')]


def normalized(db, column):
    if db.bind.dialect.name == 'sqlite':
        db.connection().connection.driver_connection.create_function('carton_material_identity', 1,
            lambda value: identity(str(value or '')), deterministic=True)
        return func.carton_material_identity(column)
    # PostgreSQL UTF-8 normalization; PostgreSQL acceptance is a separate gate.
    return func.lower(func.regexp_replace(func.trim(func.normalize(column, text('NFKC'))), '[[:space:]]+', ' ', 'g'))


def state_field(db, key):
    if db.bind.dialect.name == 'sqlite':
        return func.json_extract(CartonAuditEvent.detail_json, '$.state.' + key)
    return cast(CartonAuditEvent.detail_json, JSON)['state'][key].as_string()


def latest(db, factory, entity, keys):
    """Indexed, bounded metadata/state batch. Missing keys are cached as missing."""
    import json
    values = {}
    keys = list(dict.fromkeys(keys))
    for offset in range(0, len(keys), 400):
        part = keys[offset:offset + 400]
        sequences = select(func.max(CartonAuditEvent.sequence)).where(
            CartonAuditEvent.factory_id == factory, CartonAuditEvent.entity_type == entity,
            CartonAuditEvent.entity_id.in_(part)).group_by(CartonAuditEvent.entity_id)
        for row in db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.sequence.in_(sequences))):
            values[row.entity_id] = json.loads(row.detail_json)['state']
    return values


class AuthorityLookup(Mapping):
    """Lazy legacy adapter: schedule membership/indexing never scans folders."""
    def __init__(self,db,factory):
        self.resolver=Resolver(db,factory,'warehouse')
        self.keys=None

    def __getitem__(self,key):
        value=self.resolver.read(service().ENTITY,key)
        if value is None: raise KeyError(key)
        return value

    def __iter__(self):
        if self.keys is None:
            self.keys=list(self.resolver.db.scalars(select(CartonAuditEvent.entity_id).where(
                CartonAuditEvent.factory_id==self.resolver.factory,
                CartonAuditEvent.entity_type==service().ENTITY).distinct()))
        return iter(self.keys)

    def __len__(self):
        return len(list(iter(self)))

    def values(self):
        keys=list(iter(self))
        self.resolver.prefetch(service().ENTITY,keys)
        return [self[key] for key in keys]


def customer_for(db, factory, data):
    if data.get('customer_id'):
        customer = db.get(CartonCustomer, data['customer_id'])
        if not customer or customer.factory_id != factory:
            raise HTTPException(404, '未找到本厂客户')
        return customer
    matches = list(db.scalars(select(CartonCustomer).where(CartonCustomer.factory_id == factory,
        normalized(db, CartonCustomer.customer_code) == identity(data.get('customer_code') or ''))))
    if len(matches) != 1:
        raise HTTPException(422, '旧资料客户归属待核对，不按客户名称猜测归属')
    return matches[0]


def legacy_rows(db, factory, customer=None, contract=None):
    """Cold compatibility lookup projects identity columns, never version JSON.

    This is deliberately NOT used by the batch row-status path.
    """
    sequences = select(func.max(CartonAuditEvent.sequence)).where(CartonAuditEvent.factory_id == factory,
        CartonAuditEvent.entity_type == service().ENTITY, CartonAuditEvent.entity_id.like('CMF-%')).group_by(CartonAuditEvent.entity_id)
    query = select(CartonAuditEvent.entity_id, *[state_field(db, key) for key in
        ('customer_code', 'contract_no', 'item_no', 'po')]).where(CartonAuditEvent.sequence.in_(sequences))
    if customer:
        query = query.where(normalized(db, state_field(db, 'customer_code')) == identity(customer.customer_code))
    if contract is not None:
        query = query.where(normalized(db, state_field(db, 'contract_no')) == identity(contract))
    return [dict(id=row[0], customer_code=row[1], contract_no=row[2], item_no=row[3] or '', po=row[4] or '')
            for row in db.execute(query)]


def ambiguous(db, factory, data, target=None):
    from app.models.customer_order_ledger import OrderLedgerLine
    from app.services.carton_schedule_tracking import effective_po
    key = signature(data)
    purchases = select(CartonOrder.id).where(CartonOrder.factory_id == factory, CartonOrder.deleted_at.is_(None),
        normalized(db, CartonOrder.customer_code) == key[0], normalized(db, CartonOrder.contract_no) == key[1],
        normalized(db, CartonOrder.item_no) == key[2], normalized(db, CartonOrder.customer_po) == key[3]).limit(2)
    if len(list(db.scalars(purchases))) > 1:
        return True
    # Contract is a JSON field for ledger lines; use the same raw target adapter
    # only for this customer/product's candidate rows, not all factory orders.
    peers = db.scalars(select(OrderLedgerLine).where(OrderLedgerLine.factory_id == factory,
        normalized(db, OrderLedgerLine.product_no) == key[2], OrderLedgerLine.status == 'active',
        normalized(db, OrderLedgerLine.customer_code) == key[0]))
    count = 0
    for peer in peers:
        facts = peer.data or {}
        candidate = dict(customer_code=peer.customer_code, contract_no=facts.get('contract_no') or peer.reference_no,
            item_no=peer.product_no, po=facts.get('reference_no') or peer.reference_no or facts.get('po_no') or '')
        if signature(candidate) == key:
            count += 1
            if count > 1: return True
    if target is None or target.kind == 'SCHEDULE':
        from app.models.carton_procurement import CartonImportBatch
        import json
        if target:
            batches=[db.get(CartonImportBatch,target.id)]
        else:
            column=CartonImportBatch.parse_summary_json
            code=func.json_extract(column,'$.schedule_customer.customer_code') if db.bind.dialect.name=='sqlite' else cast(column,JSON)['schedule_customer']['customer_code'].as_string()
            batches=db.scalars(select(CartonImportBatch).where(CartonImportBatch.factory_id==factory,
                CartonImportBatch.import_type=='WEEKLY_SCHEDULE',CartonImportBatch.status!='REJECTED',normalized(db,code)==key[0]))
        for batch in batches:
            rows = json.loads(batch.parse_summary_json).get('rows', [])
            count = sum(signature(dict(customer_code=data['customer_code'], contract_no=row.get('contract_no'),
                item_no=row.get('item_no'), po=effective_po(row))) == key for row in rows)
            if count > 1: return True
    return False


class Resolver:
    def __init__(self, db, factory, audience, user=None):
        self.db, self.factory, self.audience, self.user = db, factory, audience, user
        self.cache = {}

    def prefetch(self, entity, keys):
        wanted = [key for key in keys if (entity, key) not in self.cache]
        if wanted:
            found = latest(self.db, self.factory, entity, wanted)
            self.cache.update({(entity, key): found.get(key) for key in wanted})

    def read(self, entity, key):
        self.prefetch(entity, [key])
        return copy.deepcopy(self.cache[(entity, key)])

    def find_root(self,identifier):
        root=self.read(CONTRACTS,identifier)
        if root: return root
        # A link returned by the legacy-compatible contract list must remain
        # readable before registration. Discovery is metadata-only and read-only.
        rows=[]; customer=None
        for row in legacy_rows(self.db,self.factory):
            try: candidate=customer_for(self.db,self.factory,row)
            except HTTPException: continue
            if contract_id(self.factory,candidate.id,row['contract_no'])==identifier:
                rows.append(row); customer=candidate
        if not rows: return None
        return dict(id=identifier,factory_id=self.factory,customer_id=customer.id,
            customer_code=customer.customer_code,customer_name=customer.customer_name,contract_no=rows[0]['contract_no'],
            revision=0,kind='LEGACY_MAP',authority_ids=[row['id'] for row in rows],manual_assignments={},assignments={})

    def save(self, entity, key, value, actor, action, request_id):
        service().append(self.db, actor, self.factory, key, value, action, request_id,
                         service().digest(value), entity)
        self.db.flush()
        self.cache[(entity, key)] = copy.deepcopy(value)

    def facts(self, target=None, contract=None):
        if target:
            data = service()._resolve_target(self.db, self.factory, self.audience, target, allow_ambiguous=True)
        else:
            customer = customer_for(self.db, self.factory, dict(customer_id=contract.customer_id))
            data = dict(customer_id=customer.id, customer_code=customer.customer_code, customer_name=customer.customer_name,
                contract_no=contract.contract_no, item_no=contract.item_no, po=contract.po, supplier_id='')
        customer = customer_for(self.db, self.factory, data)
        data['customer_id'] = customer.id
        root = contract_id(self.factory, customer.id, str(data.get('contract_no') or ''))
        return data, customer, root

    def new_state(self, identifier, data, root, actor, scope):
        s = service()
        rule = s.default(self.db, self.factory, data['customer_code'])
        supplier = next((row for row in s.suppliers(self.db, self.factory) if row['id'] == data.get('supplier_id')), None)
        stamp = s.now()
        state = dict(id=identifier, factory_id=self.factory, **{key:data.get(key, '') for key in
            ('customer_id', 'customer_code', 'customer_name', 'contract_no', 'item_no', 'po')},
            contract_folder_id=root, scope_kind=scope, schema_version=2, revision=1, mode=rule['mode'],
            supplier_id=supplier['id'] if supplier else '', supplier_name=supplier['name'] if supplier else '',
            status='PROCESSING', next_party=s.PARTY[self.audience], owners={s.PARTY[self.audience]:dict(id=actor.id,name=actor.display_name)},
            versions=[], approved_version_ids=[], approval=None, timeline=[], updated_at=stamp, waiting_since=stamp)
        state['timeline'].append(dict(action='CREATE', by=actor.display_name, at=stamp, note='建立合同资料记录'))
        return state

    def root(self, data, customer, actor=None, request_id='', persist=False):
        root_id = contract_id(self.factory, customer.id, data['contract_no'])
        root = self.read(CONTRACTS, root_id)
        if root:
            if root['customer_id'] != customer.id or identity(root['contract_no']) != identity(data['contract_no']):
                raise HTTPException(409, '合同规范入口归属冲突，请核对')
            return root
        old = legacy_rows(self.db, self.factory, customer, data['contract_no'])
        root = dict(id=root_id, factory_id=self.factory, customer_id=customer.id, customer_code=customer.customer_code,
            customer_name=customer.customer_name, contract_no=data['contract_no'], revision=1,
            kind='LEGACY_MAP' if old else 'NATIVE', authority_ids=[row['id'] for row in old] if old else [root_id],
            manual_assignments={},assignments={})
        if persist:
            self.save(CONTRACTS, root_id, root, actor, 'REGISTER_CONTRACT', request_id)
            if not old:
                unassigned = self.new_state(root_id, {**data,
                    'item_no':data.get('item_no','') if data.get('_contract_only') else '',
                    'po':data.get('po','') if data.get('_contract_only') else '', 'supplier_id':''}, root_id, actor, 'UNASSIGNED')
                self.save(service().ENTITY, root_id, unassigned, actor, 'CREATE', request_id)
        return root

    def member(self, root, owner_id, actor, request_id):
        if owner_id not in root['authority_ids']:
            root['authority_ids'].append(owner_id)
            root['revision'] += 1
            self.save(CONTRACTS, root['id'], root, actor, 'MAP_AUTHORITY', request_id)

    def bind(self,root,state,target,data,actor,request_id,manual=False):
        key=target_key(self.factory,target)
        existing=self.read(BINDINGS,key)
        if existing and existing['authority_id']!=state['id']:
            raise HTTPException(409,'本订单已有权威资料记录，不能另建并行映射')
        assignments=root.setdefault('assignments',{}).setdefault(state['id'],[])
        if manual and any(row['kind']==target.kind and row['key']!=key for row in assignments):
            raise HTTPException(409,'该旧夹已对应另一张同类订单，不能合并确认')
        value=dict(target=target.model_dump(),contract_folder_id=root['id'],authority_id=state['id'],
                   signature=signature(data),manual=manual)
        if not existing or existing!=value:
            self.save(BINDINGS,key,value,actor,'BIND_ORDER_MANUAL' if manual else 'BIND_ORDER',request_id)
        if not any(row['key']==key for row in assignments):
            assignments.append(dict(key=key,kind=target.kind,id=target.id,target=target.model_dump()))
        if manual: root.setdefault('manual_assignments',{})[state['id']]=True
        root['revision']+=1
        self.save(CONTRACTS,root['id'],root,actor,'MAP_ORDER',request_id)

    def resolve(self, *, target=None, contract=None, identifier=None, authority_id='', write=False,
                create=False, actor=None, request_id='', data=None, permit_ambiguity=False, contract_summary=False):
        s = service()
        binding = None
        identity_changed = False
        authority_conflict = False
        if target:
            data, customer, root_id = self.facts(target=target) if data is None else (
                data, customer_for(self.db,self.factory,data), contract_id(self.factory,data['customer_id'],data['contract_no']))
            binding = self.read(BINDINGS, target_key(self.factory,target))
            if binding and (binding['contract_folder_id'] != root_id or binding['signature'] != signature(data)):
                raise HTTPException(409, '订单归属已变更，请人工核对原资料映射')
            old_id = s.legacy_folder_id(self.factory,data)
            native_id = context_id(root_id,data)
            self.prefetch(s.ENTITY,[old_id,native_id])
            old,native = self.read(s.ENTITY,old_id),self.read(s.ENTITY,native_id)
            if old and native:
                raise HTTPException(409, '存在两个资料权威记录，归属待核对')
            state = self.read(s.ENTITY,binding['authority_id']) if binding else old or native
            if binding and not state:
                raise HTTPException(409, '原资料映射失效，请核对，不能另建并行记录')
            if state and signature(state)!=signature(data):
                raise HTTPException(409,'资料权威记录与当前订单归属不符，请人工核对')
            root = self.read(CONTRACTS,root_id)
            manual = bool(root and state and root.get('manual_assignments',{}).get(state['id']))
            blocked = (not binding and (manual or ambiguous(self.db,self.factory,data,target)))
        elif contract:
            data,customer,root_id = self.facts(contract=contract)
            data['_contract_only']=True
            root = self.read(CONTRACTS,root_id)
            state = self.read(s.ENTITY,root_id)
            blocked = False
        else:
            if not identifier or not identifier.startswith(('CMF-', 'CMF2-', 'CMO-')):
                raise HTTPException(404, '订单资料不存在')
            root = self.find_root(identifier) if identifier.startswith('CMF2-') else None
            if authority_id and (not root or not identifier.startswith('CMF2-')) and authority_id!=identifier:
                raise HTTPException(404,'请通过正确的合同规范入口选择资料记录')
            state = self.read(s.ENTITY,authority_id or identifier)
            if root and contract_summary and not authority_id and not write:
                state = None
            if root and authority_id and authority_id not in root['authority_ids']:
                raise HTTPException(404, '资料记录不属于本合同')
            if state:
                data = {key:state.get(key,'') for key in ('customer_id','customer_code','customer_name','contract_no','item_no','po','supplier_id')}
                customer = customer_for(self.db,self.factory,data)
                root_id = contract_id(self.factory,customer.id,data['contract_no'])
                if state['id'].startswith(('CMO-','CMF2-')) and state.get('contract_folder_id')!=root_id:
                    raise HTTPException(409,'资料规范归属冲突，请人工核对')
                if root and root['id'] != root_id:
                    raise HTTPException(404, '资料记录不属于本合同')
                root = self.read(CONTRACTS,root_id)
                manual = bool(root and root.get('manual_assignments',{}).get(state['id']))
                blocked = state.get('scope_kind') != 'UNASSIGNED' and not manual and ambiguous(self.db,self.factory,data)
                if state.get('scope_kind')!='UNASSIGNED':
                    old=self.read(s.ENTITY,s.legacy_folder_id(self.factory,data))
                    native=self.read(s.ENTITY,context_id(root_id,data))
                    if old and native:
                        authority_conflict=True; blocked=True
                # Old URLs must not bypass a source identity change discovered
                # by the target entry. Read history, but stop new writes until
                # its real source keys have been reconciled.
                if root:
                    from app.schemas.carton_materials import Target
                    for link in root.get('assignments',{}).get(state['id'],[]):
                        if 'target' not in link: continue
                        original=Target.model_validate(link['target'])
                        try:
                            current=s._resolve_target(self.db,self.factory,'sales' if original.kind=='LEDGER' else 'warehouse',
                                original,allow_ambiguous=True)
                            changed=signature(current)!=signature(data)
                        except HTTPException:
                            changed=True
                        if changed: identity_changed=True; blocked=True
            elif root:
                data = dict(root,item_no='',po='',supplier_id='')
                customer = customer_for(self.db,self.factory,data); root_id=root['id']; blocked=False
            else:
                raise HTTPException(404, '订单资料不存在')
        if self.user:
            check = None if not state and self.audience=='supplier' else state or data
            s.authorize(self.db,self.user,self.factory,self.audience,check,write=write)
        if identity_changed and write:
            raise HTTPException(409,'原订单来源归属已变更，请人工核对，旧URL不能绕过映射')
        if authority_conflict and write:
            raise HTTPException(409,'存在两个资料权威记录，归属待核对，旧URL不能继续写入')
        if blocked and write and not permit_ambiguity:
            raise HTTPException(422, '资料归属待核对，请先核对拆单归属并人工选定对应订单；本次未建夹或写入')
        if write and actor is not None:
            root = self.root(data,customer,actor,request_id,persist=True)
            if contract and not state and root['kind']=='NATIVE':
                state=self.read(s.ENTITY,root_id)
            if create and not state and not blocked:
                if contract and root['kind']=='LEGACY_MAP':
                    return dict(root=root,state=None,data=data,ambiguous=False)
                identifier = root_id if contract else context_id(root_id,data)
                state = self.new_state(identifier,data,root_id,actor,'UNASSIGNED' if contract else 'ORDER')
                self.save(s.ENTITY,identifier,state,actor,'CREATE',request_id)
            if state:
                self.member(root,state['id'],actor,request_id)
                # Mapping metadata only. No legacy versions, confirmations or
                # history are copied into the contract root.
                state.update(customer_id=customer.id,contract_folder_id=root_id)
                if target and not binding and not blocked:
                    self.bind(root,state,target,data,actor,request_id)
        return dict(root=root or dict(id=root_id,kind='UNREGISTERED',customer_id=customer.id),
                    state=state,data=data,ambiguous=bool(blocked))

    def view(self, entry):
        s=service(); root,state=entry['root'],entry['state']
        if state:
            from app.services.carton_material_references import hydrate
            result=s.output(hydrate(self.db,self.factory,self.audience,self.user,state),self.audience)
            result['contract_folder_id']=root['id']
            result['authority_id']=state['id']
            result['mapping_status']='REVIEW' if entry['ambiguous'] else 'RESOLVED'
            if entry['ambiguous']: result['status_label']='资料归属待核对（历史确认仍保留）'
            result['can_write']=s.writes_enabled() and not entry['ambiguous']
            if result['can_write']:
                try: s.authorize(self.db,self.user,self.factory,self.audience,state,write=True)
                except HTTPException: result['can_write']=False
            result['customer_default']=s.default(self.db,self.factory,state['customer_code']) if self.audience!='supplier' else None
            return result
        return self.contract_view(root)

    def contract_view(self, root):
        s=service(); owners=[]
        self.prefetch(s.ENTITY,root.get('authority_ids',[]))
        for identifier in root.get('authority_ids',[]):
            state=self.read(s.ENTITY,identifier)
            if not state: continue
            if self.user:
                try: s.authorize(self.db,self.user,self.factory,self.audience,state)
                except HTTPException: continue
            entry=self.resolve(identifier=identifier)
            from app.services.carton_material_references import hydrate
            value=s.output(hydrate(self.db,self.factory,self.audience,self.user,state),self.audience)
            if entry['ambiguous']: value['status_label']='资料归属待核对（历史确认仍保留）'
            owners.append(dict(authority_id=identifier,scope_kind=state.get('scope_kind','LEGACY_ORDER'),item_no=state.get('item_no',''),po=state.get('po',''),
                mapping_status='REVIEW' if entry['ambiguous'] else 'RESOLVED',
                targets=[row['target'] for row in root.get('assignments',{}).get(identifier,[]) if 'target' in row] if self.audience!='supplier' else [],
                status=value['status'],status_label=value['status_label'],revision=state['revision'],
                version_count=len(value['versions']),approved_version_ids=value['approved_version_ids'],
                current_handler=value['current_handler'],waiting_since=state.get('waiting_since','')))
        if self.audience=='supplier' and not owners:
            raise HTTPException(404,'未找到本供应商的合同资料')
        return dict(id=root['id'],contract_folder_id=root['id'],kind=root['kind'],factory_id=self.factory,
            customer_id=root['customer_id'],customer_code=root['customer_code'],customer_name=root['customer_name'],
            contract_no=root['contract_no'],revision=root['revision'],authorities=owners,
            authority_count=len(owners),order_count=sum(o['scope_kind']!='UNASSIGNED' for o in owners),
            status='CONTRACT_SUMMARY',status_label='合同资料汇总，请选择具体订单处理',
            versions=[],approved_version_ids=[],approval=None,timeline=[],can_write=False,
            next_party='',current_handler='',item_no='',po='',mode='UNDECIDED',supplier_id='',supplier_name='')
