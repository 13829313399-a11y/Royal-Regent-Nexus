"""Explicit cutover, mutually exclusive opening balances and transaction replay."""
from datetime import datetime, time, timezone, timedelta
from sqlalchemy import select, func
from app.models import spray_ops as m
from .common import add,get,scoped,serialize,require,timestamp
from . import production as p


def policy(db,f):
    return db.scalar(scoped(db,m.SprayOpsHistoryPolicy,f))


def create_policy(db,f,b):
    require(b.expected_version==0 and policy(db,f) is None,'history_policy_frozen','切换口径一经确认不可改写')
    # A policy cannot retroactively reinterpret existing stock movements.
    require(not db.scalar(select(func.count()).select_from(m.SprayOpsMovement).where(m.SprayOpsMovement.factory_id==f,m.SprayOpsMovement.business_date<=str(b.cutoff))),'history_existing_movements','截止日内已有实物流转，须先核对，不能追溯设定期初')
    row=add(db,m.SprayOpsHistoryPolicy,f,mode=b.mode,cutoff=str(b.cutoff),evidence=b.evidence)
    return serialize(row)


def guard_date(db,f,day):
    selected=policy(db,f)
    require(not selected or selected.mode!='opening' or str(day)>selected.cutoff,'opening_replay_conflict','已采用期初结余，截止日及以前不能再重放库存、生产或费用交易')


def create_opening(db,f,b):
    selected=policy(db,f)
    require(b.expected_version==0 and selected and selected.mode=='opening' and selected.cutoff==str(b.business_date),'opening_policy','期初登记日期必须等于已确认的期初截止日')
    line=get(db,m.SprayOpsDemandLine,f,b.line_id)
    demand=get(db,m.SprayOpsDemand,f,line.demand_id)
    require(demand.status=='confirmed','demand_not_confirmed','期初结余须关联已确认订单')
    require(line.route_id,'route_unconfirmed','期初必须确认工艺版本')
    route=get(db,m.SprayOpsRoute,f,line.route_id)
    require(route.status=='confirmed','route_unconfirmed','期初工艺未确认')
    steps=p.rows(db,m.SprayOpsStep,f,route_id=route.id)
    done=set(b.completed_step_ids)
    require(done <= {step.id for step in steps},'opening_steps','期初工序不属于该路线')
    require(len(done)==len(b.completed_step_ids),'opening_steps','期初工序重复')
    for step_id in done:
        require({edge.predecessor_id for edge in p.rows(db,m.SprayOpsPredecessor,f,step_id=step_id)} <= done,'opening_predecessors','期初完成工序缺少前序完成依据')
    require((b.state=='white' and not done) or (b.state=='finished' and done=={step.id for step in steps}) or (b.state=='wip' and bool(done) and len(done)<len(steps)),'opening_state','期初状态与完成工序集合不一致')
    require(b.unit==line.unit and all(step.output_ratio==1 and step.input_unit==step.output_unit==line.unit for step in steps),'opening_conversion','含单位转换的期初须逐批迁移核对，不允许推断套件关系')
    p.piece_quantity(b.quantity,b.unit)
    prior=sum(item.quantity for item in p.rows(db,m.SprayOpsOpening,f,line_id=line.id))
    require(prior+b.quantity<=line.quantity,'opening_quantity','同订单期初累计不能超过需求')
    # Opening lots are explicitly distinguished from received inbound lots.
    batch=add(db,m.SprayOpsBatch,f,kind='opening',document_no='OPEN:'+b.document_no,line_id=line.id,item_no=line.item_no,part=line.part,quantity=b.quantity,accepted=b.quantity,held=0,rejected=0,unit=b.unit,business_date=str(b.business_date),source_ref=b.source_ref)
    at=timestamp(datetime.combine(b.business_date+timedelta(days=1),time(),tzinfo=timezone(timedelta(hours=8))))
    stock=p.make_stock(db,f,batch.id,line.id,b.quantity,b.unit,b.state,at,done)
    opening=add(db,m.SprayOpsOpening,f,document_no=b.document_no,business_date=str(b.business_date),line_id=line.id,stock_id=stock.id,quantity=b.quantity,unit=b.unit,evidence=b.evidence,source_ref=b.source_ref)
    p.movement(db,f,None,stock,b.quantity,b.quantity,'opening',opening.id,b.business_date,b.evidence)
    return {**serialize(opening),'stock':serialize(stock)}
