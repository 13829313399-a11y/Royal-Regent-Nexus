"""Independent A-factory UV domain. No relationship targets retired UV tables."""
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, Column, ForeignKeyConstraint, Integer, JSON, LargeBinary, Numeric, String, Text, UniqueConstraint, Index
from app.db import Base

FACTORY = "huakang-a"
DECIMAL = Numeric(18, 6)


def now():
    return datetime.now(UTC).isoformat()


def scoped(*refs, checks=(), unique=()):
    return (
        CheckConstraint("factory_id = 'huakang-a'"), UniqueConstraint("factory_id", "id"),
        *(ForeignKeyConstraint(["factory_id", field], [f"uv_ops_{table}.factory_id", f"uv_ops_{table}.id"]) for field, table in refs),
        *(CheckConstraint(value) for value in checks),
        *(UniqueConstraint("factory_id", *fields) for fields in unique),
    )


class Record:
    id = Column(String(64), primary_key=True, default=lambda: uuid4().hex)
    factory_id = Column(String(32), nullable=False, default=FACTORY, index=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(String(40), nullable=False, default=now)
    updated_at = Column(String(40), nullable=False, default=now)
    created_by = Column(String(64), nullable=False, default="system")


class UvOpsSettings(Record, Base):
    __tablename__ = "uv_ops_settings"
    timezone = Column(String(64), nullable=False, default="Asia/Shanghai")
    currency = Column(String(3), nullable=False, default="CNY")
    stale_seconds = Column(Integer, nullable=False, default=120)
    data_mode = Column(String(24), nullable=False, default="live")
    __table_args__ = scoped(unique=(("factory_id",),))


class UvOpsReceipt(Record, Base):
    __tablename__ = "uv_ops_receipts"
    actor_id = Column(String(64), nullable=False)
    operation_id = Column(String(64), nullable=False)
    action = Column(String(128), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    permissions = Column(JSON, nullable=False)
    result = Column(JSON, nullable=False, default=dict)
    __table_args__ = scoped(unique=(("actor_id", "operation_id"),))


class UvOpsAudit(Record, Base):
    __tablename__ = "uv_ops_audit"
    actor_id = Column(String(64), nullable=False)
    operation_id = Column(String(64), nullable=False)
    action = Column(String(128), nullable=False)
    entity_id = Column(String(64), nullable=False, index=True)
    reason = Column(Text, nullable=False, default="")
    __table_args__ = scoped()


class UvOpsMachine(Record, Base):
    __tablename__ = "uv_ops_machines"
    code = Column(String(64), nullable=False)
    name = Column(String(128), nullable=False)
    model = Column(String(128), nullable=False, default="")
    width_mm = Column(DECIMAL)
    height_mm = Column(DECIMAL)
    ink_family = Column(String(64), nullable=False, default="unknown")
    maintenance = Column(Boolean, nullable=False, default=False)
    capability_evidence = Column(Text, nullable=False, default="")
    __table_args__ = scoped(unique=(("code",),), checks=("width_mm IS NULL OR width_mm > 0", "height_mm IS NULL OR height_mm > 0"))


class UvOpsFixture(Record, Base):
    __tablename__ = "uv_ops_fixtures"
    code = Column(String(64), nullable=False)
    revision = Column(Integer, nullable=False)
    slots = Column(Integer, nullable=False)
    width_mm = Column(DECIMAL, nullable=False)
    height_mm = Column(DECIMAL, nullable=False)
    __table_args__ = scoped(unique=(("code", "revision"),), checks=("slots > 0", "width_mm > 0", "height_mm > 0"))


class UvOpsProduct(Record, Base):
    __tablename__ = "uv_ops_products"
    code = Column(String(64), nullable=False)
    name = Column(String(128), nullable=False)
    customer = Column(String(128), nullable=False, default="")
    __table_args__ = scoped(unique=(("code",),))


class UvOpsProcessVersion(Record, Base):
    __tablename__ = "uv_ops_process_versions"
    product_id = Column(String(64), nullable=False)
    fixture_id = Column(String(64), nullable=False)
    revision = Column(Integer, nullable=False)
    name = Column(String(128), nullable=False)
    ink_family = Column(String(64), nullable=False)
    pieces_per_board = Column(Integer, nullable=False)
    cycle_seconds = Column(DECIMAL)
    width_mm = Column(DECIMAL, nullable=False)
    height_mm = Column(DECIMAL, nullable=False)
    faces = Column(Integer, nullable=False, default=1)
    passes = Column(Integer, nullable=False, default=1)
    __table_args__ = scoped(("product_id", "products"), ("fixture_id", "fixtures"), unique=(("product_id", "revision"),), checks=("pieces_per_board > 0", "faces > 0", "passes > 0", "width_mm > 0", "height_mm > 0", "cycle_seconds IS NULL OR cycle_seconds > 0"))


class UvOpsFileVersion(Record, Base):
    __tablename__ = "uv_ops_file_versions"
    process_version_id = Column(String(64), nullable=False)
    role = Column(String(24), nullable=False)
    name = Column(String(200), nullable=False)
    sha256 = Column(String(64), nullable=False)
    mime = Column(String(80), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    content = Column(LargeBinary, nullable=False)
    confirmed_by = Column(String(64))
    confirmed_at = Column(String(40))
    first_article_evidence = Column(Text)
    __table_args__ = scoped(("process_version_id", "process_versions"), checks=("role IN ('artwork','preview','production')", "size_bytes > 0"))


class UvOpsPricePolicy(Record, Base):
    __tablename__ = "uv_ops_price_policies"
    product_id = Column(String(64), nullable=False)
    basis = Column(String(24), nullable=False)
    rate = Column(DECIMAL, nullable=False)
    currency = Column(String(3), nullable=False)
    rectangle_area = Column(Boolean, nullable=False, default=False)
    measured_area_m2 = Column(DECIMAL)
    evidence = Column(Text, nullable=False)
    __table_args__ = scoped(("product_id", "products"), checks=("rate >= 0", "basis IN ('piece','area')", "measured_area_m2 IS NULL OR measured_area_m2 > 0"))


class UvOpsWagePolicy(Record, Base):
    __tablename__ = "uv_ops_wage_policies"
    name = Column(String(128), nullable=False)
    basis = Column(String(24), nullable=False)
    rate = Column(DECIMAL, nullable=False)
    bonus_rate = Column(DECIMAL, nullable=False, default=0)
    currency = Column(String(3), nullable=False)
    evidence = Column(Text, nullable=False)
    __table_args__ = scoped(checks=("rate >= 0", "bonus_rate >= 0", "basis IN ('piece','hour','base_bonus')"))


class UvOpsDemand(Record, Base):
    __tablename__ = "uv_ops_demands"
    code = Column(String(64), nullable=False)
    product_id = Column(String(64), nullable=False)
    source_type = Column(String(32), nullable=False, default="manual")
    source_line_id = Column(String(128))
    customer_snapshot = Column(String(128), nullable=False, default="")
    product_snapshot = Column(String(128), nullable=False)
    quantity = Column(Integer, nullable=False)
    allocated = Column(Integer, nullable=False, default=0)
    cancelled = Column(Integer, nullable=False, default=0)
    due_at = Column(String(40), nullable=False)
    priority = Column(Integer, nullable=False, default=0)
    __table_args__ = scoped(("product_id", "products"), unique=(("code",), ("source_type", "source_line_id")), checks=("quantity > 0", "allocated >= 0", "cancelled >= 0", "allocated + cancelled <= quantity"))


class UvOpsTask(Record, Base):
    __tablename__ = "uv_ops_tasks"
    code = Column(String(64), nullable=False)
    demand_id = Column(String(64), nullable=False)
    process_version_id = Column(String(64), nullable=False)
    file_version_id = Column(String(64), nullable=False)
    wage_policy_id = Column(String(64))
    price_policy_id = Column(String(64))
    parent_task_id = Column(String(64))
    quantity = Column(Integer, nullable=False)
    status = Column(String(24), nullable=False, default="ready")
    product_snapshot = Column(String(128), nullable=False)
    process_snapshot = Column(JSON, nullable=False)
    cost_price_snapshot = Column(JSON)
    payroll_policy_snapshot = Column(JSON)
    __table_args__ = scoped(("demand_id", "demands"), ("process_version_id", "process_versions"), ("file_version_id", "file_versions"), ("price_policy_id", "price_policies"), ("wage_policy_id", "wage_policies"), ("parent_task_id", "tasks"), unique=(("code",),), checks=("quantity > 0",))


class UvOpsScheduleBlock(Record, Base):
    __tablename__ = "uv_ops_schedule_blocks"
    machine_id = Column(String(64), nullable=False, index=True)
    task_id = Column(String(64), nullable=False)
    batch_id = Column(String(64))  # Null only for preserved legacy whole-task plans.
    fixture_id = Column(String(64))
    fixture_evidence = Column(Text)
    estimate_basis = Column(String(24), nullable=False, default="standard", server_default="standard")
    estimated_seconds = Column(DECIMAL)
    estimate_reason = Column(Text)
    start_at = Column(String(40), nullable=False, index=True)
    end_at = Column(String(40), nullable=False)
    fixed = Column(Boolean, nullable=False, default=False)
    status = Column(String(24), nullable=False, default="planned")
    __table_args__ = (*scoped(("machine_id", "machines"), ("task_id", "tasks"), ("batch_id", "batches"), ("fixture_id", "fixtures"), checks=("end_at > start_at",)),
        UniqueConstraint("factory_id", "task_id", "batch_id", name="uq_uv_ops_schedule_task_batch"),
        CheckConstraint("estimate_basis IN ('standard','manual')", name="ck_uv_ops_schedule_estimate_basis"),
        CheckConstraint("estimated_seconds IS NULL OR estimated_seconds > 0", name="ck_uv_ops_schedule_estimated_seconds"))


class UvOpsShift(Record, Base):
    __tablename__ = "uv_ops_shifts"
    name = Column(String(128), nullable=False)
    business_date = Column(String(10), nullable=False, index=True)
    start_at = Column(String(40), nullable=False)
    end_at = Column(String(40), nullable=False)
    breaks = Column(JSON, nullable=False, default=list)
    status = Column(String(24), nullable=False, default="open")
    close_reason = Column(Text)
    __table_args__ = scoped(checks=("end_at > start_at", "status IN ('open','closed')"))


class UvOpsParticipation(Record, Base):
    __tablename__ = "uv_ops_participations"
    active_key = Column(Integer, nullable=True, default=1, server_default='1')
    shift_id = Column(String(64), nullable=False)
    task_id = Column(String(64), nullable=False)
    employee_id = Column(String(64), nullable=False)
    employee_name = Column(String(128), nullable=False)
    start_at = Column(String(40), nullable=False)
    end_at = Column(String(40), nullable=False)
    role_coefficient = Column(DECIMAL, nullable=False, default=1)
    __table_args__ = scoped(("shift_id", "shifts"), ("task_id", "tasks"), checks=("end_at > start_at", "role_coefficient > 0"))


class UvOpsWorker(Record, Base):
    __tablename__ = "uv_ops_workers"
    employee_id = Column(String(64), nullable=False)
    name = Column(String(128), nullable=False)
    __table_args__ = scoped(unique=(("employee_id",),))


class UvOpsBatch(Record, Base):
    __tablename__ = "uv_ops_batches"
    task_id = Column(String(64), nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    quantity = Column(Integer, nullable=False)
    pass_index = Column(Integer, nullable=False, default=1)
    remaining = Column(Integer, nullable=False)
    intermediate = Column(Integer, nullable=False, default=0)
    good = Column(Integer, nullable=False, default=0)
    rework = Column(Integer, nullable=False, default=0)
    scrap = Column(Integer, nullable=False, default=0)
    pending = Column(Integer, nullable=False, default=0)
    reserved = Column(Integer, nullable=False, default=0)
    received = Column(Integer, nullable=False, default=0)
    __table_args__ = scoped(("task_id", "tasks"), checks=("quantity > 0", "remaining >= 0", "intermediate >= 0", "good >= 0", "rework >= 0", "scrap >= 0", "pending >= 0", "reserved >= 0", "received >= 0", "remaining + intermediate + good + rework + scrap + pending = quantity", "reserved + received <= good"))


class UvOpsBatchRelation(Record, Base):
    __tablename__ = "uv_ops_batch_relations"
    source_id = Column(String(64), nullable=False)
    target_id = Column(String(64), nullable=False)
    quantity = Column(Integer, nullable=False)
    kind = Column(String(24), nullable=False)
    __table_args__ = scoped(("source_id", "batches"), ("target_id", "batches"), checks=("quantity > 0", "source_id != target_id"))


class UvOpsReworkBinding(Record, Base):
    __tablename__ = 'uv_ops_rework_bindings'
    task_id = Column(String(64), nullable=False)
    batch_id = Column(String(64), nullable=False)
    __table_args__ = scoped(('task_id','tasks'),('batch_id','batches'),unique=(('task_id',),))


class UvOpsProductionEntry(Record, Base):
    __tablename__ = "uv_ops_production_entries"
    task_id = Column(String(64), nullable=False)
    batch_id = Column(String(64), nullable=False)
    shift_id = Column(String(64), nullable=False)
    business_date = Column(String(10), nullable=False, index=True)
    pass_index = Column(Integer, nullable=False)
    source_bucket = Column(String(24), nullable=False)
    processed = Column(Integer, nullable=False)
    good = Column(Integer, nullable=False)
    rework = Column(Integer, nullable=False)
    scrap = Column(Integer, nullable=False)
    pending = Column(Integer, nullable=False)
    final_pass = Column(Boolean, nullable=False)
    direction = Column(Integer, nullable=False, default=1)
    reversal_of = Column(String(64))
    evidence = Column(Text, nullable=False)
    __table_args__ = scoped(("task_id", "tasks"), ("batch_id", "batches"), ("shift_id", "shifts"), ("reversal_of", "production_entries"), unique=(("reversal_of",),), checks=("processed = good + rework + scrap + pending", "processed > 0", "good >= 0", "rework >= 0", "scrap >= 0", "pending >= 0", "direction IN (-1,1)"))


class UvOpsQualityEntry(Record, Base):
    __tablename__ = "uv_ops_quality_entries"
    active_key = Column(Integer, nullable=True, default=1, server_default='1')
    batch_id = Column(String(64), nullable=False)
    task_id = Column(String(64), nullable=False)
    production_entry_id = Column(String(64), nullable=False)
    shift_id = Column(String(64), nullable=False)
    business_date = Column(String(10), nullable=False, index=True)
    pass_index = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=False)
    disposition = Column(String(24), nullable=False)
    evidence = Column(Text, nullable=False)
    __table_args__ = scoped(("batch_id", "batches"), ("task_id", "tasks"), ("production_entry_id", "production_entries"), ("shift_id", "shifts"), checks=("quantity > 0", "disposition IN ('good','rework','scrap')"))


class UvOpsHandover(Record, Base):
    __tablename__ = "uv_ops_handovers"
    batch_id = Column(String(64), nullable=False)
    target = Column(String(128), nullable=False)
    receiver_id = Column(String(64), nullable=False)
    business_date = Column(String(10), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    received = Column(Integer, nullable=False, default=0)
    rejected = Column(Integer, nullable=False, default=0)
    returned = Column(Integer, nullable=False, default=0)
    status = Column(String(24), nullable=False, default="pending")
    __table_args__ = scoped(("batch_id", "batches"), checks=("quantity > 0", "received >= 0", "rejected >= 0", "returned >= 0", "received + rejected <= quantity", "returned <= received"))


class UvOpsHandoverEvent(Record, Base):
    __tablename__ = "uv_ops_handover_events"
    handover_id = Column(String(64), nullable=False)
    kind = Column(String(24), nullable=False)
    quantity = Column(Integer, nullable=False)
    business_date = Column(String(10), nullable=False)
    evidence = Column(Text, nullable=False)
    __table_args__ = scoped(("handover_id", "handovers"), checks=("quantity > 0",))


class UvOpsInkSku(Record, Base):
    __tablename__ = "uv_ops_ink_skus"
    code = Column(String(64), nullable=False)
    supplier = Column(String(128), nullable=False)
    model = Column(String(128), nullable=False)
    ink_family = Column(String(64), nullable=False)
    color = Column(String(32), nullable=False)
    capacity_ml = Column(DECIMAL, nullable=False)
    __table_args__ = scoped(unique=(("code",),), checks=("capacity_ml > 0",))


class UvOpsInkBalance(Record, Base):
    __tablename__ = "uv_ops_ink_balances"
    sku_id = Column(String(64), nullable=False)
    lot = Column(String(64), nullable=False)
    location = Column(String(64), nullable=False)
    quantity_ml = Column(DECIMAL, nullable=False, default=0)
    cost_value = Column(DECIMAL, nullable=False, default=0)
    currency = Column(String(3), nullable=False)
    __table_args__ = scoped(("sku_id", "ink_skus"), unique=(("sku_id", "lot", "location"),), checks=("quantity_ml >= 0", "cost_value >= 0"))


class UvOpsInkMovement(Record, Base):
    __tablename__ = "uv_ops_ink_movements"
    balance_id = Column(String(64), nullable=False)
    other_balance_id = Column(String(64))
    task_id = Column(String(64))
    kind = Column(String(24), nullable=False)
    quantity_ml = Column(DECIMAL, nullable=False)
    cost_value = Column(DECIMAL, nullable=False)
    currency = Column(String(3), nullable=False)
    business_date = Column(String(10), nullable=False, index=True)
    reversal_of = Column(String(64))
    evidence = Column(Text, nullable=False)
    __table_args__ = scoped(("balance_id", "ink_balances"), ("other_balance_id", "ink_balances"), ("task_id", "tasks"), ("reversal_of", "ink_movements"), unique=(("reversal_of",),), checks=("quantity_ml > 0", "cost_value >= 0"))


class UvOpsExpense(Record, Base):
    __tablename__ = "uv_ops_expenses"
    active_key = Column(Integer, nullable=True, default=1, server_default='1')
    category = Column(String(32), nullable=False)
    task_id = Column(String(64))
    cost_amount = Column(DECIMAL, nullable=False)
    currency = Column(String(3), nullable=False)
    business_date = Column(String(10), nullable=False, index=True)
    allocation_end = Column(String(10))
    evidence = Column(Text, nullable=False)
    __table_args__ = scoped(("task_id", "tasks"), checks=("cost_amount >= 0", "category IN ('direct','department','investment')"))


class UvOpsWageAccrual(Record, Base):
    __tablename__ = "uv_ops_wage_accruals"
    active_key = Column(Integer, nullable=True, default=1, server_default='1')
    shift_id = Column(String(64), nullable=False)
    task_id = Column(String(64), nullable=False)
    business_date = Column(String(10), nullable=False, index=True)
    payroll_amount = Column(DECIMAL, nullable=False)
    currency = Column(String(3), nullable=False)
    payroll_evidence = Column(JSON, nullable=False)
    __table_args__ = scoped(("shift_id", "shifts"), ("task_id", "tasks"), unique=(("shift_id", "task_id", "active_key"),), checks=("payroll_amount >= 0",))


class UvOpsWageAllocation(Record, Base):
    __tablename__ = "uv_ops_wage_allocations"
    accrual_id = Column(String(64), nullable=False)
    employee_id = Column(String(64), nullable=False)
    payroll_weight_seconds = Column(DECIMAL, nullable=False)
    payroll_amount = Column(DECIMAL, nullable=False)
    __table_args__ = scoped(("accrual_id", "wage_accruals"), unique=(("accrual_id", "employee_id"),), checks=("payroll_amount >= 0", "payroll_weight_seconds >= 0"))


class UvOpsPeriod(Record, Base):
    __tablename__ = "uv_ops_periods"
    period = Column(String(7), nullable=False)
    status = Column(String(24), nullable=False, default="open")
    close_reason = Column(Text)
    __table_args__ = scoped(unique=(("period",),), checks=("status IN ('open','closed')",))


class UvOpsReportSnapshot(Record, Base):
    __tablename__ = "uv_ops_report_snapshots"
    period_id = Column(String(64), nullable=False)
    report = Column(JSON, nullable=False)
    ledger_revision = Column(String(128), nullable=False)
    __table_args__ = scoped(("period_id", "periods"))


class UvOpsAgent(Record, Base):
    __tablename__ = "uv_ops_agents"
    name = Column(String(128), nullable=False)
    token_hash = Column(String(64), unique=True)
    pairing_hash = Column(String(64), unique=True)
    pairing_expires_at = Column(String(40))
    enrollment_id = Column(String(64))
    enrollment_pairing_hash = Column(String(64))
    revoked = Column(Boolean, nullable=False, default=False)
    last_seen_at = Column(String(40))
    diagnostics = Column(JSON, nullable=False, default=dict)
    __table_args__ = scoped()


class UvOpsSourceBinding(Record, Base):
    __tablename__ = "uv_ops_source_bindings"
    agent_id = Column(String(64), nullable=False)
    machine_id = Column(String(64), nullable=False)
    source_id = Column(String(64), nullable=False)
    adapter_type = Column(String(64), nullable=False)
    binding_version = Column(Integer, nullable=False)
    active_key = Column(String(64), unique=True)
    active_source_key = Column(String(64), unique=True)
    capabilities = Column(JSON, nullable=False, default=dict)
    __table_args__ = scoped(("agent_id", "agents"), ("machine_id", "machines"), unique=(("agent_id", "source_id", "binding_version"),))


class UvOpsAgentEventInbox(Record, Base):
    __tablename__ = "uv_ops_agent_event_inbox"
    agent_id = Column(String(64), nullable=False)
    machine_id = Column(String(64), nullable=False)
    binding_id = Column(String(64), nullable=False)
    event_id = Column(String(64), nullable=False)
    stream_id = Column(String(64), nullable=False)
    sequence = Column(Integer, nullable=False)
    observed_at = Column(String(40), nullable=False)
    received_at = Column(String(40), nullable=False, default=now)
    kind = Column(String(32), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    evidence = Column(JSON, nullable=False)
    late_closed_period = Column(Boolean, nullable=False, default=False)
    resolved_by = Column(String(64))
    __table_args__ = scoped(("agent_id", "agents"), ("machine_id", "machines"), ("binding_id", "source_bindings"), unique=(("agent_id", "event_id"), ("agent_id", "stream_id", "sequence")))


class UvOpsSourceCursor(Record, Base):
    __tablename__ = "uv_ops_source_cursors"
    binding_id = Column(String(64), nullable=False)
    stream_id = Column(String(64), nullable=False)
    sequence = Column(Integer, nullable=False, default=0)
    observed_at = Column(String(40), nullable=False)
    work_state = Column(String(24), nullable=False, default="unknown")
    progress = Column(DECIMAL)
    progress_meaning = Column(String(32), nullable=False, default="unknown")
    native_job_id = Column(String(128))
    __table_args__ = scoped(("binding_id", "source_bindings"), unique=(("binding_id",),))


class UvOpsRun(Record, Base):
    __tablename__ = "uv_ops_runs"
    machine_id = Column(String(64), nullable=False)
    binding_id = Column(String(64), nullable=False)
    native_job_id = Column(String(128), nullable=False)
    native_identity = Column(String(64), nullable=False)
    last_sequence = Column(Integer, nullable=False, default=0)
    last_stream_id = Column(String(64))
    last_binding_version = Column(Integer, nullable=False, default=0)
    last_observed_at = Column(String(40), nullable=False)
    file_name = Column(String(200), nullable=False, default="")
    file_hash = Column(String(64))
    task_token = Column(String(64))
    started_at = Column(String(40), nullable=False)
    ended_at = Column(String(40))
    state = Column(String(24), nullable=False, default="running")
    raw_count = Column(DECIMAL)
    count_unit = Column(String(16), nullable=False, default="unknown")
    counter_mode = Column(String(24), nullable=False, default="unknown")
    ink_total_ml = Column(DECIMAL)
    match_evidence = Column(Text)
    __table_args__ = scoped(("machine_id", "machines"), ("binding_id", "source_bindings"), unique=(("native_identity",),))


class UvOpsRunAllocation(Record, Base):
    __tablename__ = "uv_ops_run_allocations"
    run_id = Column(String(64), nullable=False)
    task_id = Column(String(64), nullable=False)
    batch_id = Column(String(64), nullable=False)
    pass_index = Column(Integer, nullable=False)
    slots = Column(JSON, nullable=False)
    full_boards = Column(Integer, nullable=False)
    tail_pieces = Column(Integer, nullable=False)
    share = Column(DECIMAL, nullable=False)
    __table_args__ = scoped(("run_id", "runs"), ("task_id", "tasks"), ("batch_id", "batches"), unique=(("run_id", "task_id", "batch_id", "pass_index"),), checks=("full_boards >= 0", "tail_pieces >= 0", "share > 0", "share <= 1"))


class UvOpsImportJob(Record, Base):
    __tablename__ = "uv_ops_import_jobs"
    actor_id = Column(String(64), nullable=False)
    template = Column(String(32), nullable=False)
    file_hash = Column(String(64), nullable=False)
    field_mapping = Column(JSON, nullable=False, default=dict)
    units_confirmed = Column(Boolean, nullable=False, default=False)
    rows = Column(JSON, nullable=False)
    errors = Column(JSON, nullable=False)
    status = Column(String(24), nullable=False, default="preview")
    source_name = Column(String(200),nullable=False,default='')
    source_content = Column(LargeBinary)
    warnings = Column(JSON,nullable=False,default=list)
    results = Column(JSON,nullable=False,default=list)
    lease_until = Column(String(40))
    __table_args__ = scoped()


class UvOpsImportRow(Record, Base):
    __tablename__ = "uv_ops_import_rows"
    identity = Column(String(64), nullable=False)
    job_id = Column(String(64), nullable=False)
    entity_id = Column(String(64), nullable=False)
    __table_args__ = scoped(("job_id", "import_jobs"), unique=(("identity",),))


class UvOpsExportJob(Record, Base):
    __tablename__ = "uv_ops_export_jobs"
    actor_id = Column(String(64), nullable=False)
    kind = Column(String(32), nullable=False)
    filters = Column(JSON, nullable=False)
    permissions = Column(JSON, nullable=False)
    status = Column(String(24), nullable=False, default="queued")
    lease_until = Column(String(40))
    row_count = Column(Integer, nullable=False, default=0)
    artifact = Column(LargeBinary)
    error = Column(String(64))
    __table_args__ = scoped()


class UvOpsReferenceEfficiency(Record, Base):
    __tablename__ = 'uv_ops_reference_efficiency'
    name = Column(String(128),nullable=False)
    pieces_per_board = Column(Integer,nullable=False)
    cycle_seconds = Column(DECIMAL,nullable=False)
    available_seconds = Column(DECIMAL,nullable=False)
    cost_amount = Column(DECIMAL)
    currency = Column(String(3),nullable=False)
    evidence = Column(Text,nullable=False)
    __table_args__ = scoped(checks=('pieces_per_board > 0','cycle_seconds > 0','available_seconds > 0','cost_amount >= 0'))


class UvOpsRunCost(Record, Base):
    __tablename__ = 'uv_ops_run_costs'
    active_key = Column(Integer, nullable=True, default=1, server_default='1')
    run_id = Column(String(64),nullable=False)
    business_date = Column(String(10),nullable=False)
    cost_amount = Column(DECIMAL,nullable=False)
    currency = Column(String(3),nullable=False)
    evidence = Column(Text,nullable=False)
    cost_allocations = Column(JSON,nullable=False)
    __table_args__ = scoped(('run_id','runs'),unique=(('run_id','active_key'),),checks=('cost_amount >= 0',))


Index('ix_uv_ops_inbox_machine_observed',UvOpsAgentEventInbox.factory_id,UvOpsAgentEventInbox.machine_id,UvOpsAgentEventInbox.observed_at)
Index('ix_uv_ops_runs_machine_started',UvOpsRun.factory_id,UvOpsRun.machine_id,UvOpsRun.started_at)
Index('ix_uv_ops_runs_recent',UvOpsRun.factory_id,UvOpsRun.created_at.desc(),UvOpsRun.id)
Index('ix_uv_ops_runs_unmatched',UvOpsRun.factory_id,UvOpsRun.match_evidence,UvOpsRun.started_at)
Index('ix_uv_ops_production_task_date',UvOpsProductionEntry.factory_id,UvOpsProductionEntry.task_id,UvOpsProductionEntry.business_date)
Index('ix_uv_ops_schedule_machine_time',UvOpsScheduleBlock.factory_id,UvOpsScheduleBlock.machine_id,UvOpsScheduleBlock.start_at,UvOpsScheduleBlock.end_at)


class UvOpsReversal(Record, Base):
    __tablename__ = 'uv_ops_reversals'
    kind = Column(String(32), nullable=False)
    entity_id = Column(String(64), nullable=False)
    business_date = Column(String(10), nullable=False)
    reason = Column(Text, nullable=False)
    __table_args__ = scoped(unique=(('kind','entity_id'),), checks=("kind IN ('quality','expense','wage','run_cost','participation')",))


class UvOpsExecution(Record, Base):
    __tablename__ = 'uv_ops_executions'
    task_id = Column(String(64), nullable=False)
    batch_id = Column(String(64), nullable=False)
    machine_id = Column(String(64), nullable=False)
    schedule_id = Column(String(64), nullable=False)
    fixture_code = Column(String(64), nullable=False)
    shift_id = Column(String(64), nullable=False)
    started_at = Column(String(40), nullable=False)
    ended_at = Column(String(40))
    start_evidence = Column(Text, nullable=False)
    end_evidence = Column(Text)
    ended_shift_id = Column(String(64))
    active_key = Column(Integer, default=1, server_default='1')
    __table_args__ = scoped(('task_id','tasks'), ('batch_id','batches'), ('machine_id','machines'), ('schedule_id','schedule_blocks'), ('shift_id','shifts'), ('ended_shift_id','shifts'), unique=(('batch_id','active_key'),('machine_id','active_key'),('fixture_code','active_key')), checks=("ended_at IS NULL OR ended_at > started_at", "(active_key = 1 AND ended_at IS NULL) OR (active_key IS NULL AND ended_at IS NOT NULL)"))
