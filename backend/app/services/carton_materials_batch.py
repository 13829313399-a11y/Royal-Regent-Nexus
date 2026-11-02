"""Atomic, explicit per-order reference approval. No schema or projection writes."""
import copy
import json

from fastapi import HTTPException

from app.services import carton_materials as materials
from app.services.carton_materials_resolver import Resolver

KIND='MATERIAL_APPROVAL_BATCH_V1'


def approve(db,user,factory,audience,body,refresh):
    try:
        actor=materials.locked(db,user,factory,audience,refresh)
        if audience=='supplier': raise HTTPException(403,'供应商不能批量确认资料可用')
        identifiers=[item.context_id for item in body.targets]
        if len(set(identifiers))!=len(identifiers): raise HTTPException(422,'同一目标不可在批次中重复')
        resolver=Resolver(db,factory,audience,actor)
        resolver.prefetch(materials.ENTITY,identifiers)
        states={}
        # Read-only resolver phase: no compatibility registration or business write.
        for identifier in sorted(identifiers):
            state=resolver.resolve(identifier=identifier,write=True)['state']
            if not state or state['id']!=identifier or state.get('scope_kind')=='UNASSIGNED':
                raise HTTPException(422,'请选择具体目标订单；合同汇总和未分配资料不可批量确认')
            if state.get('hidden') or state.get('is_archived'): raise HTTPException(404,'目标资料不可写')
            states[identifier]=state
        targets=sorted([dict(context_id=item.context_id,revision=item.revision,
                             version_ids=sorted(item.version_ids),note=item.note.strip()) for item in body.targets],
                       key=lambda item:item['context_id'])
        fingerprint=materials.digest(dict(action=KIND,actor_id=actor.id,factory_id=factory,audience=audience,targets=targets))
        receipt_id='CMR-'+materials.digest([actor.id,body.request_id])
        receipts=materials.events(db,factory,materials.REQUESTS,receipt_id)
        previous=json.loads(receipts[-1].detail_json) if receipts else None
        if previous and (previous['fingerprint']!=fingerprint or previous['state'].get('kind')!=KIND):
            raise HTTPException(409,'此操作编号已用于不同目标、版本或确认内容')
        plans=[]
        for target in targets:
            state=states[target['context_id']]
            plan=materials.approval_plan(db,actor,factory,audience,state,target['revision'],target['version_ids'],target['note'],
                references_only=True,replaying=bool(previous),allow_stale_duplicate=True)
            plans.append((target,state,plan))
        if previous:
            # Historical acknowledgement, never reapply after later state changes.
            db.rollback()  # Release IAM/factory locks without any new business write.
            return copy.deepcopy(previous['state']['result'])
        items=[]
        for target,state,plan in plans:
            audit=None
            if not plan['duplicate']:
                order_request=materials.digest([KIND,actor.id,body.request_id,state['id']])
                order_fingerprint=materials.digest(dict(batch_fingerprint=fingerprint,target=target))
                audit=materials.apply_approval(db,actor,factory,audience,state,plan,order_request,order_fingerprint,
                    batch_receipt_id=receipt_id)
            items.append(dict(context_id=state['id'],revision=state['revision'],version_ids=plan['version_ids'],
                approval=copy.deepcopy(state['approval']),changed=not plan['duplicate'],
                event_sequence=audit.sequence if audit is not None else None))
        result=dict(batch_receipt_id=receipt_id,request_id=body.request_id,actor_id=actor.id,
                    count=len(items),changed_count=sum(item['changed'] for item in items),
                    unchanged_count=sum(not item['changed'] for item in items),items=items)
        evidence=dict(kind=KIND,actor_id=actor.id,factory_id=factory,audience=audience,
                      request_id=body.request_id,targets=targets,result=result)
        materials.append(db,actor,factory,receipt_id,evidence,'BATCH_APPROVE',body.request_id,fingerprint,materials.REQUESTS)
        db.commit()
        return result
    except BaseException:
        db.rollback()
        raise
