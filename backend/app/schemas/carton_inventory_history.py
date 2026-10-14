"""Paged carton movement history, without changing the legacy list contract."""

from pydantic import BaseModel

from app.schemas.carton_procurement import CartonInventoryMovementOut


class CartonInventoryHistoryMovementOut(CartonInventoryMovementOut):
    # Computed from the full factory ledger, even when the reversal is on another page.
    is_reversed: bool = False


class CartonInventoryHistoryListOut(BaseModel):
    factory_id: str
    total: int
    limit: int
    offset: int
    items: list[CartonInventoryHistoryMovementOut]
