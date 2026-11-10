"""Only immutable source files are used by the independent JP trial."""
from sqlalchemy import LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class OrderLedgerSource(Base):
    __tablename__ = "order_ledger_sources"
    __table_args__ = (UniqueConstraint("factory_id", "customer_code", "sha256", "kind", name="uq_order_ledger_source"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    customer_code: Mapped[str] = mapped_column(String(64))
    sha256: Mapped[str] = mapped_column(String(64))
    file_name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(24))
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
