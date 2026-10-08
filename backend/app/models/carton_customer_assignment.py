"""Customer responsibilities narrow existing carton order rights, never grant them."""
from sqlalchemy import ForeignKey, ForeignKeyConstraint, Index, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class CartonCustomerAssignment(Base):
    __tablename__ = "carton_customer_assignments"
    __table_args__ = (
        ForeignKeyConstraint(["customer_id", "factory_id"], ["carton_customers.id", "carton_customers.factory_id"],
                             ondelete="CASCADE", name="fk_carton_assignment_customer_factory"),
        Index("ix_carton_assignment_factory_user", "factory_id", "user_id"),
    )
    customer_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("auth_users.id", ondelete="CASCADE"), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))


class CartonCustomerOwner(Base):
    """The claimant may delegate customer work, never IAM permissions."""
    __tablename__ = "carton_customer_owners"
    __table_args__ = (
        ForeignKeyConstraint(["customer_id", "factory_id"], ["carton_customers.id", "carton_customers.factory_id"],
                             ondelete="CASCADE", name="fk_carton_owner_customer_factory"),
    )
    customer_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("auth_users.id", ondelete="CASCADE"))
