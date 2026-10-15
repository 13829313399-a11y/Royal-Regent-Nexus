from typing import Annotated, Literal
from pydantic import Field
from app.services.cutting_schemas import Command, Quantity, Text, Strict
from app.services.cutting_planning_schemas import BusinessDate


class MaterialRequest(Command):
    task_id: Text
    plan_version: Annotated[int, Field(strict=True, ge=1)]
    row: Annotated[int, Field(strict=True, ge=0, le=299)]
    material_id: Text
    material_revision: Annotated[int, Field(strict=True, ge=1)]
    quantity: Quantity
    business_date: BusinessDate
    due_date: BusinessDate | None = None
    mapping_basis: Annotated[str, Field(min_length=4, max_length=500)]


class MaterialReceipt(Command):
    original_id: Text
    quantity: Quantity
    business_date: BusinessDate


class MaterialDecision(Command):
    original_id: Text
    business_date: BusinessDate


class RecoverMaterial(Strict):
    action: Literal['request', 'receive', 'void', 'close', 'reuse']
    command: dict


class MaterialReuse(MaterialDecision):
    plan_version: Annotated[int, Field(strict=True, ge=1)]
