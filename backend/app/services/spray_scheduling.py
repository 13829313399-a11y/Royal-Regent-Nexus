"""Finite-capacity suggestions split across actual working intervals."""
from datetime import timedelta
from decimal import Decimal as D, ROUND_DOWN
from sqlalchemy import select
from fastapi import HTTPException
from app.models import spray_production as m
from app.services import spray_production as s
from app.services.spray_advanced import eligible, check_shared


def slots(db, factory, resource, earliest, occupied):
    shared_ids = {v["id"] for v in resource.shared_requirements}
    related = [v for v in occupied if v["resource_id"] == resource.id or shared_ids & {x["id"] for x in v.get("shared_allocations", [])}]
    shared = [s.find(db,m.SpraySharedResource,factory,ident) for ident in shared_ids]
    result = []
    for window in sorted(resource.calendar,key=lambda w:w["start"]):
        window_offset=len(result)
        start,end=max(earliest,s.instant(window["start"])),s.instant(window["end"])
        if start>=end: continue
        boundaries={start,end}
        for v in related:
            boundaries.update(t for t in (s.instant(v["start_at"]),s.instant(v["end_at"])) if start<t<end)
        for item in shared:
            for w in item.calendar:
                boundaries.update(t for t in (s.instant(w["start"]),s.instant(w["end"])) if start<t<end)
        points=sorted(boundaries)
        for a,b in zip(points,points[1:]):
            if any(v["resource_id"]==resource.id and a<s.instant(v["end_at"]) and b>s.instant(v["start_at"]) for v in related): continue
            try: check_shared(db,factory,resource.shared_requirements,a,b,related)
            except HTTPException: continue
            if len(result)>window_offset and result[-1][1]==a: result[-1]=(result[-1][0],b)
            else: result.append((a,b))
    return result


def suggest(db, factory, actor, p):
    earliest=s.instant(p.get("start_at"))
    candidates=list(db.execute(select(m.SprayBatch,m.SprayOrderLine,m.SprayOrder).join(m.SprayOrderLine,m.SprayBatch.line_id==m.SprayOrderLine.id).join(m.SprayOrder,m.SprayOrderLine.order_id==m.SprayOrder.id).where(m.SprayBatch.factory_id==factory,m.SprayOrder.status=="active").order_by(m.SprayOrder.priority.desc(),m.SprayOrder.due_date,m.SprayBatch.created_at).limit(200)))
    resources=list(db.scalars(select(m.SprayResource).where(m.SprayResource.factory_id==factory).order_by(m.SprayResource.name)))
    occupied=[s.serial(t) for t in db.scalars(select(m.SprayTask).where(m.SprayTask.factory_id==factory,m.SprayTask.status.in_(["planned","running","paused"])))]
    changes,skipped=[],[]
    for batch,line,order in candidates:
        for state,qty in s.stock(db,factory,batch.id).items():
            options=eligible(db,factory,line.id,state)
            if qty<=0 or not options: continue
            if not line.prep_ready_at:
                skipped.append({"batch_id":batch.id,"reason":"备产未完成","remaining":str(qty)});continue
            ready_at=max(earliest,s.instant(line.prep_ready_at))
            for movement in db.scalars(select(m.SprayMovement).where(m.SprayMovement.batch_id==batch.id,m.SprayMovement.to_state==state,m.SprayMovement.available_at!="")):
                ready_at=max(ready_at,s.instant(movement.available_at))
            remaining=qty
            while remaining>0 and len(changes)<200:
                choices=[]
                for step in options:
                    for resource in resources:
                        if resource.capability!=step.capability or not resource.machine_rate or not resource.person_minutes:continue
                        rate=min(resource.machine_rate,D(resource.workers)*60/resource.person_minutes)
                        for start,end in slots(db,factory,resource,ready_at,occupied+changes):
                            hours=D(str((end-start).total_seconds()))/3600-resource.setup_hours
                            capacity=(max(D(0),hours)*rate).quantize(D(".000001"),rounding=ROUND_DOWN)
                            quantity=min(remaining,capacity)
                            if quantity<=0:continue
                            finish=start+timedelta(seconds=float((quantity/rate+resource.setup_hours)*3600))
                            choices.append((finish,start,resource.name,step.sequence,resource,step,quantity))
                            break
                if not choices:break
                finish,start,_,_,resource,step,quantity=min(choices,key=lambda v:v[:4])
                candidate={"batch_id":batch.id,"step_id":step.id,"resource_id":resource.id,"quantity":str(quantity),"workers":resource.workers,"start_at":start.isoformat(),"input_state":state,"shared_allocations":resource.shared_requirements}
                changes=s.plan_changes(db,factory,changes+[candidate])
                remaining-=quantity
            if remaining>0:
                skipped.append({"batch_id":batch.id,"reason":"可用班次/节拍/共享人员工装不足，未安排量保留待排","remaining":str(remaining)})
    if not changes:s.fail("没有满足实收、前置、等待、班次和共享资源条件的可排批次")
    result=s.preview_plan(db,factory,actor,{"changes":changes})
    result.update(skipped=skipped,strategy="优先级与交期 → 最早完成；按班次空档拆批，设备与共享人员/工装共同约束",
                  comparison={"retained_tasks":len(occupied),"new_tasks":len(changes),"scheduled_quantity":str(sum((D(v["quantity"]) for v in changes),D(0))),"late_tasks":sum(v["late"] for v in changes),"unallocated_batches":len(skipped)})
    return result
