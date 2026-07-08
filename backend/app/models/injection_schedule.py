from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class InjectionScheduleImportBatch(Base):
    __tablename__ = "injection_schedule_import_batches"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    import_type: Mapped[str] = mapped_column(String(32), default="daily_schedule")
    source_file_name: Mapped[str] = mapped_column(String(255), default="")
    business_date: Mapped[str] = mapped_column(String(20), default="")
    status: Mapped[str] = mapped_column(String(32), default="imported", index=True)
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[str] = mapped_column(String(32), default="")

    machines: Mapped[list["InjectionScheduleMachine"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="InjectionScheduleMachine.source_row",
    )
    tasks: Mapped[list["InjectionScheduleTask"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="InjectionScheduleTask.source_row",
    )
    issues: Mapped[list["InjectionScheduleImportIssue"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="InjectionScheduleImportIssue.source_row",
    )


class InjectionScheduleMachine(Base):
    __tablename__ = "injection_schedule_machines"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("injection_schedule_import_batches.id", ondelete="CASCADE"),
        index=True,
    )
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    machine_code: Mapped[str] = mapped_column(String(64), index=True)
    workshop: Mapped[str] = mapped_column(String(64), default="")
    machine_spec_label: Mapped[str] = mapped_column(String(128), default="")
    machine_process_type: Mapped[str] = mapped_column(String(64), default="")
    robot_type: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="available")
    constraints_json: Mapped[str] = mapped_column(Text, default="{}")
    source_row: Mapped[int] = mapped_column(Integer, default=0)

    batch: Mapped[InjectionScheduleImportBatch] = relationship(back_populates="machines")


class InjectionScheduleTask(Base):
    __tablename__ = "injection_schedule_tasks"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("injection_schedule_import_batches.id", ondelete="CASCADE"),
        index=True,
    )
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    source_row: Mapped[int] = mapped_column(Integer, default=0, index=True)
    assigned_machine_code: Mapped[str] = mapped_column(String(64), default="", index=True)
    task_bucket: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    mold_code: Mapped[str] = mapped_column(String(128), default="")
    product_name: Mapped[str] = mapped_column(String(255), default="")
    order_no: Mapped[str] = mapped_column(String(128), default="")
    product_code: Mapped[str] = mapped_column(String(128), default="")
    machine_model: Mapped[str] = mapped_column(String(128), default="")
    color: Mapped[str] = mapped_column(String(128), default="")
    pigment: Mapped[str] = mapped_column(String(128), default="")
    material: Mapped[str] = mapped_column(String(128), default="")
    order_qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    produced_qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    shortage_qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    daily_target_qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    delivery_due_date: Mapped[str] = mapped_column(String(32), default="")
    plan_start_at: Mapped[str] = mapped_column(String(32), default="")
    plan_finish_at: Mapped[str] = mapped_column(String(32), default="")
    warehouse_due_at: Mapped[str] = mapped_column(String(32), default="")
    delivery_gap_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    priority_flag: Mapped[str] = mapped_column(String(32), default="")
    remark: Mapped[str] = mapped_column(Text, default="")
    source_values_json: Mapped[str] = mapped_column(Text, default="{}")

    batch: Mapped[InjectionScheduleImportBatch] = relationship(back_populates="tasks")


class InjectionScheduleImportIssue(Base):
    __tablename__ = "injection_schedule_import_issues"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("injection_schedule_import_batches.id", ondelete="CASCADE"),
        index=True,
    )
    source_row: Mapped[int] = mapped_column(Integer, default=0, index=True)
    severity: Mapped[str] = mapped_column(String(20), default="info")
    issue_type: Mapped[str] = mapped_column(String(64), index=True)
    field_name: Mapped[str] = mapped_column(String(64), default="")
    raw_value: Mapped[str] = mapped_column(Text, default="")
    message: Mapped[str] = mapped_column(Text, default="")

    batch: Mapped[InjectionScheduleImportBatch] = relationship(back_populates="issues")
