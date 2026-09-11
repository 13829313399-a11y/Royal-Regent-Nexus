"""Process precedence, shared capacity and employee-shift settlement rules."""
from collections import defaultdict
from decimal import Decimal as D, ROUND_HALF_UP
from hashlib import sha256
import json
from sqlalchemy import select
from app.models import spray_production as m
from app.services import spray_production as s


def build_graph(db, factory, line, inputs, created):
    if not any("predecessors" in v for v in inputs):
        return
    keys = [str(v.get("key", i + 1)) for i, v in enumerate(inputs)]
    if len(set(keys)) != len(keys):
        s.fail("工艺节点代号不能重复")
    graph = {key: [str(x) for x in v.get("predecessors", [])] for key, v in zip(keys, inputs)}
    for key, deps in graph.items():
        if len(set(deps)) != len(deps) or key in deps or any(x not in graph for x in deps):
            s.fail("前置工序必须引用本部件其他有效节点")
    done = set()
    while len(done) < len(graph):
        available = {key for key, deps in graph.items() if key not in done and set(deps) <= done}
        if not available:
            s.fail("工艺图存在循环，请检查前置关系")
        done |= available
    ids = dict(zip(keys, [x.id for x in created]))
    for key, step in zip(keys, created):
        step.predecessors = [ids[x] for x in graph[key]]
    line.graph_route = True


def initial_state(db, factory, line_id):
    line = s.find(db, m.SprayOrderLine, factory, line_id)
    return "route:" if line.graph_route else s.ready(s.steps(db, factory, line_id)[0])


def completed(state):
    # Defect states retain the exact progress of the affected physical pieces.
    route = state.split(":", 2)[2] if state.startswith(("held:", "rework:")) and state.count(":") >= 2 else state
    return set(filter(None, route.removeprefix("route:").split(","))) if route.startswith("route:") else set()


def eligible(db, factory, line_id, state):
    all_steps = s.steps(db, factory, line_id)
    if state.startswith(("ready:", "rework:")):
        return [x for x in all_steps if x.id == state.split(":")[1]]
    if not state.startswith("route:"):
        return []
    done = completed(state)
    return [x for x in all_steps if x.id not in done and set(x.predecessors) <= done]


def progress(db, factory, step, source):
    line = s.find(db, m.SprayOrderLine, factory, step.line_id)
    if not line.graph_route:
        return s.next_state(db, factory, step)
    done = completed(source) | {step.id}
    all_ids = {x.id for x in s.steps(db, factory, line.id)}
    if not done <= all_ids:
        s.fail("工艺状态包含未知节点", 409)
    return "finished" if done == all_ids else "route:" + ",".join(sorted(done))


def defect(step, source, kind):
    suffix = ":route:" + ",".join(sorted(completed(source))) if source.startswith("route:") or ":route:" in source else ""
    return f"{kind}:{step.id}{suffix}"


def create_shared(db, factory, actor, p):
    if p.get("kind") not in ("person", "tool"):
        s.fail("共享资源请选择人员或工装")
    capacity = 1 if p["kind"] == "person" else s.headcount(p.get("capacity", 1))
    calendar = p.get("calendar", [])
    intervals = sorted((s.instant(w["start"]), s.instant(w["end"])) for w in calendar)
    if not intervals or any(a >= b or (i and a < intervals[i-1][1]) for i, (a,b) in enumerate(intervals)):
        s.fail("共享资源须有不重叠的可用日历")
    item = s.add(db, m.SpraySharedResource, factory, actor, name=s.text(p.get("name"), "资源名称", 128), kind=p["kind"], capacity=capacity,
                 calendar=[{"start": a.isoformat(), "end": b.isoformat()} for a,b in intervals])
    return {"id": item.id}


def requirements(db, factory, values):
    if not isinstance(values, list) or len(values) > 100:
        s.fail("共享资源明细无效")
    result, seen = [], set()
    for v in values:
        resource = s.find(db, m.SpraySharedResource, factory, v.get("id"))
        qty = s.headcount(v.get("quantity", 1))
        if resource.id in seen or qty > resource.capacity:
            s.fail("共享资源重复或数量超过配置")
        seen.add(resource.id)
        result.append({"id": resource.id, "quantity": qty})
    return result


def update_resource(db,factory,actor,p):
    resource=s.find(db,m.SprayResource,factory,p.get("id"))
    if resource.revision!=p.get("expected_revision"):s.fail("资源配置已变化，请刷新",409)
    intervals=sorted((s.instant(w["start"]),s.instant(w["end"])) for w in p.get("calendar",[]))
    if not intervals or any(a>=b or (i and a<intervals[i-1][1]) for i,(a,b) in enumerate(intervals)):s.fail("日历须提供不重叠的有效班次")
    for task in db.scalars(select(m.SprayTask).where(m.SprayTask.factory_id==factory,m.SprayTask.resource_id==resource.id,m.SprayTask.status.in_(["planned","running","paused"]))):
        if not any(s.instant(task.start_at)>=a and s.instant(task.end_at)<=b for a,b in intervals):s.fail("新日历影响已有任务，请先改排受影响任务",409)
    resource.calendar=[{"start":a.isoformat(),"end":b.isoformat()} for a,b in intervals]
    resource.shared_requirements=requirements(db,factory,p.get("shared_requirements",[]))
    resource.revision+=1
    return {"id":resource.id}


def check_shared(db, factory, allocations, start, end, occupied):
    for allocation in allocations:
        item = s.find(db, m.SpraySharedResource, factory, allocation["id"])
        if not any(start >= s.instant(w["start"]) and end <= s.instant(w["end"]) for w in item.calendar):
            s.fail(f"{item.name} 不在可用班次内", 409)
        events = [(start, allocation["quantity"]), (end, -allocation["quantity"])]
        for task in occupied:
            a, b = s.instant(task["start_at"]), s.instant(task["end_at"])
            if a >= end or b <= start:
                continue
            for used in task.get("shared_allocations", []):
                if used["id"] == item.id:
                    events.extend([(max(a,start), used["quantity"]), (min(b,end), -used["quantity"])])
        level = 0
        for _, delta in sorted(events, key=lambda e:(e[0], e[1])):
            level += delta
            if level > item.capacity:
                s.fail(f"共享{ '人员' if item.kind == 'person' else '工装'} {item.name} 同时占用超量", 409)


def payroll_preview(db, factory, p):
    business_date, shift = s.day(p.get("business_date")), s.text(p.get("shift"), "班次", 32)
    policy = s.find(db, m.SprayRate, factory, p.get("policy_id"))
    if policy.rule_code != "employee_shift_guarantee" or policy.effective_date > business_date:
        s.fail("请选择当日已生效的员工班次保底策略")
    regular_rate = s.number(policy.parameters.get("regular_hour_rate", 0))
    overtime_rate = s.number(policy.parameters.get("overtime_hour_rate", 0))
    employees = {}
    pending = []
    report_ids = []
    query = select(m.SprayReportLine, m.SprayReport).join(m.SprayReport, m.SprayReportLine.report_id == m.SprayReport.id).where(
        m.SprayReport.factory_id == factory, m.SprayReport.business_date == business_date, m.SprayReport.shift == shift, m.SprayReport.status == "confirmed")
    for line, head in db.execute(query):
        if line.calculation.get("currency", policy.currency) != policy.currency:
            continue
        report_ids.append(line.id)
        if line.wage_status != "verified":
            pending.append({"report_line_id": line.id, "reason": "报工工资未正式定价"})
        shares = line.calculation.get("allocations", ["0"] * len(line.people))
        for person, share in zip(line.people, shares):
            employee = str(person.get("employee_id") or person["name"]).strip()
            e = employees.setdefault(employee, {"employee": employee, "name":person["name"], "regular_hours": D(0), "overtime_hours":D(0), "earned":D(0), "tasks":[]})
            rh, oh = s.number(person.get("regular_hours", line.regular_hours)), s.number(person.get("overtime_hours", line.overtime_hours))
            e["regular_hours"] += rh
            e["overtime_hours"] += oh
            e["earned"] += D(share)
            e["tasks"].append({"report_line_id":line.id, "task_id":line.task_id, "amount": share, "regular_hours":str(rh), "overtime_hours":str(oh)})
    output = []
    for e in employees.values():
        if e["regular_hours"] + e["overtime_hours"] > 24:
            pending.append({"employee":e["employee"], "reason":"员工本班多任务工时合计超过 24 小时"})
        guarantee = (e["regular_hours"] * regular_rate + e["overtime_hours"] * overtime_rate).quantize(D(".01"), rounding=ROUND_HALF_UP)
        difference = guarantee - e["earned"]
        subsidy = max(D(0), difference)
        output.append({**{k:str(v) if isinstance(v,D) else v for k,v in e.items()}, "guarantee":str(guarantee), "signed_difference":str(difference), "subsidy":str(subsidy), "payable":str(e["earned"]+subsidy)})
    result = {"business_date":business_date, "shift":shift, "currency":policy.currency, "policy_id":policy.id, "policy_revision":policy.revision,
              "employees":sorted(output,key=lambda x:x["employee"]), "pending":pending, "report_line_ids":sorted(report_ids), "amount":str(sum((D(x["payable"]) for x in output),D(0)))}
    result["fingerprint"] = sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    result["confirmable"] = bool(output) and not pending and policy.status == "active"
    return result


def close_payroll(db, factory, actor, p):
    preview = payroll_preview(db, factory, p)
    if not preview["confirmable"]:
        s.fail("还有未核工资、无员工明细或策略尚未正式采用")
    if preview["fingerprint"] != p.get("fingerprint"):
        s.fail("员工班次工资已变化，请重新预览", 409)
    record = s.add(db, m.SprayPayroll, factory, actor, **{k:preview[k] for k in ("business_date","shift","currency","policy_id","amount")}, snapshot=preview)
    for employee in preview["employees"]:
        s.add(db,m.SprayPayrollLine,factory,actor,payroll_id=record.id,
              **{k:employee[k] for k in ("employee","name","regular_hours","overtime_hours","earned","guarantee","signed_difference","subsidy","payable")},source_lines=employee["tasks"])
    return {"id":record.id}


def check_payroll_open(db, factory, business_date, shift):
    if db.scalar(select(m.SprayPayroll.id).where(m.SprayPayroll.factory_id == factory, m.SprayPayroll.business_date == business_date, m.SprayPayroll.shift == shift)):
        s.fail("本班工资已确认，不能回改或追加报工；请在开放班次登记差额并引用原记录",409)


def adjustment(db, factory, actor, p):
    old = s.find(db, m.SpraySettlement, factory, p.get("settlement_id"))
    business_date = s.day(p.get("business_date"))
    if business_date[:7] <= old.period:
        s.fail("已月结差额须记入后续开放期间")
    s.frozen(db,factory,old.customer,business_date,old.currency)
    amount = s.number(p.get("amount"),signed=True).quantize(D(".01"),rounding=ROUND_HALF_UP)
    if not amount:
        s.fail("差额不能为零")
    item=s.add(db,m.SprayAdjustment,factory,actor,settlement_id=old.id,business_date=business_date,amount=amount,
               document_no=s.text(p.get("document_no"),"调整凭据",128),reason=s.text(p.get("reason"),"调整依据",2000))
    return {"id":item.id}
