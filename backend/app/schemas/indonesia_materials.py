"""Typed inputs for the Heyuan-to-Indonesia materials domain."""
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Number = Annotated[Decimal, Field(ge=0, le=Decimal('1000000000000'), max_digits=24, decimal_places=8, allow_inf_nan=False)]
Positive = Annotated[Decimal, Field(gt=0, le=Decimal('1000000000000'), max_digits=24, decimal_places=8, allow_inf_nan=False)]


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Command(Input):
    factory_id: Text
    operation_id: Annotated[str, StringConstraints(min_length=16, max_length=64)]
    action: Literal['draft_transfer', 'option_save', 'option_delete', 'option_restore', 'customer_delete', 'customer_restore', 'product_delete', 'product_restore', 'material_restore', 'customer_save', 'material_save', 'product_save', 'order_save', 'order_plan_save', 'order_materials_sync', 'order_recalculate', 'demand_adjust', 'supply_save', 'supply_reply', 'output_material_refresh', 'receipt_confirm', 'allocate', 'reallocate', 'shipment_save', 'shipment_confirm', 'import_confirm', 'warehouse_import_confirm', 'master_import_confirm']
    entity_id: str | None = Field(None, max_length=64)
    expected_version: int = Field(0, ge=0)
    data: dict = Field(default_factory=dict)


class Transfer(Input):
    assignee_id: Text
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class Customer(Input):
    name: Text
    status: Literal['active', 'inactive'] = 'active'
    notes: str = Field('', max_length=500)


class CustomsRule(Input):
    basis: Literal['quantity', 'weight']
    divisor: Positive


class Material(Input):
    code: str = Field('', max_length=160)
    name: Text
    english_name: str = Field('', max_length=200)
    specification: str = Field('', max_length=400)
    category: str = Field('', max_length=100)
    unit: Text
    customs_unit: Text = 'KGM'
    customs_rule: CustomsRule | None = None
    net_weight_kg: Number | None = None
    billing_weight_kg: Number | None = None  # Legacy API compatibility; new master saves derive this from net weight.
    billing_basis: Literal['quantity', 'weight'] = 'quantity'
    billing_mode: Literal['manual', 'automatic'] = 'manual'
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


class ProductMaterial(Input):
    material_id: Text | None = None
    usage: Positive
    material: Material | None = None
    material_version: int = Field(0, ge=0)

    @model_validator(mode='after')
    def validate_source(self):
        if not self.material_id and self.material is None:
            raise ValueError('请选择已有物料或填写新物料资料')
        if self.material is not None and bool(self.material_id) != (self.material_version > 0):
            raise ValueError('修改已有物料须提供原版本；新增物料版本须为零')
        return self


class MaterialDeletion(Input):
    material_id: Text
    expected_version: int = Field(gt=0)


class Product(Input):
    code: Text
    customer: Text
    customer_id: str | None = Field(None, max_length=64)
    name: str = Field('', max_length=200)
    unit: Text = 'PCS'
    daily_capacity: Positive | None = None
    transport_days: int = Field(25, ge=0, le=3650)
    materials: list[ProductMaterial] = Field(default_factory=list, max_length=100)
    material_deletions: list[MaterialDeletion] = Field(default_factory=list, max_length=100)


class MasterSheetMapping(Input):
    sheet: Text
    header_row: int = Field(ge=1, le=30)
    columns: dict[str, int] = Field(max_length=20)
    enabled: bool = True


class MasterImportContext(Input):
    product_ids: list[Text] = Field(min_length=1, max_length=50)
    mappings: list[MasterSheetMapping] = Field(default_factory=list, max_length=30)


class MasterImportRecipe(Input):
    product_id: Text
    decision: Literal['keep', 'import']
    usage: Positive | None = None


class MasterImportChoice(Input):
    group: int = Field(ge=0)
    source_index: int = Field(ge=0)
    decision: Literal['keep', 'import']
    material: Material | None = None
    recipes: list[MasterImportRecipe] = Field(min_length=1, max_length=50)


class MasterImportSelection(Input):
    choices: list[MasterImportChoice] = Field(min_length=1, max_length=500)


class Order(Input):
    customer: Text
    recipient: Literal['RRI', 'RRM']
    contract_no: Text
    po_no: str = Field('', max_length=160)
    item_no: Text
    batch: str = Field('', max_length=160)  # Retained only for historical delivery identities.
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
    billing_mode: Literal['manual', 'automatic'] = 'manual'
    billing_factor: Positive = Decimal(1)
    billing_weight_source: Literal['net_weight_kg'] | None = None  # Missing on legacy commands/retries.
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


class PlanningMaterial(Input):
    material_id: Text
    expected_version: int = Field(gt=0)
    procurement_days: int | None = Field(default=None, ge=0, le=3650)


class OrderPlan(Input):
    product_id: Text
    product_version: int = Field(gt=0)
    daily_capacity: Positive
    transport_days: int = Field(ge=0, le=3650)
    materials: list[PlanningMaterial] = Field(min_length=1, max_length=200)
    sync_materials: bool = False  # Old durable planning commands keep their original scope.


class MaterialSyncVersion(Input):
    id: Text
    expected_version: int = Field(gt=0)


class OrderMaterialsSync(Input):
    customer: Text
    recipient: Literal['RRI', 'RRM']
    item_no: str = Field('', max_length=160)
    # The workspace itself is bounded to 5,000 records. References are deduplicated.
    orders: list[MaterialSyncVersion] = Field(min_length=1, max_length=5000)
    products: list[MaterialSyncVersion] = Field(min_length=1, max_length=5000)
    materials: list[MaterialSyncVersion] = Field(min_length=1, max_length=5000)


class WarehouseAllocation(Input):
    order_id: Text
    demand_id: Text
    order_version: int = Field(gt=0)
    normal_quantity: Number
    spare_quantity: Number = Decimal(0)


class WarehouseAllocationRef(Input):
    allocation_id: Text
    version: int = Field(gt=0)


class WarehouseRowSelection(Input):
    index: int = Field(ge=0)
    material_id: Text
    material_version: int = Field(gt=0)
    supply_id: str | None = Field(None, max_length=64)
    supply_version: int = Field(0, ge=0)
    purchase: dict = Field(default_factory=dict)
    allocations: list[WarehouseAllocation] = Field(min_length=1, max_length=100)
    replace_allocations: list[WarehouseAllocationRef] = Field(default_factory=list, max_length=1000)
    replacement_reason: str = Field('', max_length=500)


class WarehouseSelection(Input):
    shipment_date: date
    rows: list[WarehouseRowSelection] = Field(min_length=1, max_length=200)


class ReceiptTemplateRow(Input):
    order_id: Text
    demand_id: Text


class ReceiptTemplate(Input):
    factory_id: Text
    customer: Text
    recipient: Literal['RRI', 'RRM']
    warehouse: str = Field('', max_length=160)
    mode: Literal['order', 'summary'] = 'order'
    selections: list[ReceiptTemplateRow] = Field(default_factory=list, max_length=200)
    material_ids: list[Text] = Field(default_factory=list, max_length=200)
    item_no: str = Field('', max_length=160)

    @model_validator(mode='after')
    def selection_mode(self):
        if self.mode == 'order' and (not self.selections or self.material_ids or self.item_no):
            raise ValueError('订单模板须选择合同物料')
        if self.mode == 'summary' and (not self.material_ids or self.selections):
            raise ValueError('汇总模板须选择物料，不按合同拆行')
        return self
