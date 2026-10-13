"""Typed inputs for the Heyuan-to-Indonesia materials domain."""
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Number = Annotated[Decimal, Field(ge=0, le=Decimal('1000000000000'), max_digits=24, decimal_places=8, allow_inf_nan=False)]
Positive = Annotated[Decimal, Field(gt=0, le=Decimal('1000000000000'), max_digits=24, decimal_places=8, allow_inf_nan=False)]


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Command(Input):
    factory_id: Text
    operation_id: Annotated[str, StringConstraints(min_length=16, max_length=64)]
    action: Literal['material_save', 'product_save', 'order_save', 'order_recalculate', 'demand_adjust', 'supply_save', 'supply_reply', 'output_material_refresh', 'receipt_confirm', 'allocate', 'reallocate', 'shipment_save', 'shipment_confirm', 'import_confirm']
    entity_id: str | None = Field(None, max_length=64)
    expected_version: int = Field(0, ge=0)
    data: dict = Field(default_factory=dict)


class Material(Input):
    code: Text
    name: Text
    english_name: str = Field('', max_length=200)
    specification: str = Field('', max_length=400)
    category: str = Field('', max_length=100)
    unit: Text
    customs_unit: Text = 'KGM'
    net_weight_kg: Number | None = None
    billing_weight_kg: Number | None = None
    billing_basis: Literal['quantity', 'weight'] = 'quantity'
    billing_unit: Text = 'PCS'
    billing_factor: Positive = Decimal(1)
    price: Number = Decimal(0)
    currency: Text = 'USD'
    procurement_days: int | None = Field(None, ge=0, le=3650)
    supplier: str = Field('', max_length=200)
    usage: str = Field('', max_length=300)
    department: str = Field('', max_length=100)
    export_company: str = Field('', max_length=200)
    image_data: str = Field('', max_length=2000000)


class Recipe(Input):
    material_id: Text
    usage: Positive


class Product(Input):
    code: Text
    customer: Text
    name: str = Field('', max_length=200)
    unit: Text = 'PCS'
    daily_capacity: Positive | None = None
    transport_days: int = Field(25, ge=0, le=3650)
    materials: list[Recipe] = Field(default_factory=list, max_length=100)


class Order(Input):
    customer: Text
    recipient: Literal['RRI', 'RRM']
    contract_no: Text
    po_no: str = Field('', max_length=160)
    item_no: Text
    batch: Text
    quantity: Positive
    unit: Text = 'PCS'
    delivery_date: date
    reason: str = Field('', max_length=500)


class Supply(Input):
    material_id: Text
    purchase_no: Text
    purchase_line: Text
    purchase_date: date
    supplier: Text
    purchase_quantity: Positive
    normal_quantity: Number
    spare_quantity: Number = Decimal(0)
    batch: Text
    price: Number
    currency: Text = 'USD'
    billing_basis: Literal['quantity', 'weight'] = 'quantity'
    billing_factor: Positive = Decimal(1)
    promised_date: date | None = None


class Receipt(Input):
    actual_date: date


class Reply(Input):
    promised_date: date
    reason: Text


class Adjust(Input):
    demand_id: Text
    quantity: Number
    reason: Text


class Allocation(Input):
    supply_id: Text
    order_id: Text
    demand_id: Text
    normal_quantity: Number
    spare_quantity: Number = Decimal(0)
    reason: str = Field('', max_length=500)


class Reallocation(Input):
    order_id: Text
    demand_id: Text
    normal_quantity: Number
    spare_quantity: Number = Decimal(0)
    reason: Text


class ShipmentLine(Input):
    allocation_id: Text
    normal_quantity: Number
    spare_quantity: Number = Decimal(0)


class PackItem(Input):
    allocation_id: Text
    normal_quantity: Number
    spare_quantity: Number = Decimal(0)


class Package(Input):
    label: Text
    cartons: int = Field(ge=1, le=1000000)
    length_cm: Positive
    width_cm: Positive
    height_cm: Positive
    carton_weight_kg: Number
    pallet: str = Field('', max_length=80)
    items: list[PackItem] = Field(min_length=1, max_length=200)


class Shipment(Input):
    customer: Text
    recipient: Literal['RRI', 'RRM']
    shipment_date: date
    lines: list[ShipmentLine] = Field(min_length=1, max_length=200)
    packages: list[Package] = Field(default_factory=list, max_length=200)
    remarks: str = Field('', max_length=1000)


class ImportSelection(Input):
    indexes: list[int] = Field(min_length=1, max_length=2000)


class Reason(Input):
    reason: Text
