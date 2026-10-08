"""Read-only query helpers shared by the carton workspaces."""
from datetime import date, timedelta
from fastapi import HTTPException


def literal_pattern(value):
    return "%" + value.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"


def date_bounds(start="", end=""):
    try:
        first = date.fromisoformat(start) if start else None
        last = date.fromisoformat(end) if end else None
        if first and last and first > last:
            raise ValueError()
        return (first.isoformat() + "T00:00:00" if first else "",
                (last + timedelta(days=1)).isoformat() + "T00:00:00" if last else "")
    except (ValueError, OverflowError):
        raise HTTPException(422, "日期范围无效，请检查起止日期")


AUDIT_LABELS = {
    "CUSTOMER_CREATED": "客户建档", "CUSTOMER_UPDATED": "客户资料维护", "CUSTOMER_DELETED": "客户删除",
    "MASTER_RULE_RECOVERED": "恢复交期规则", "MASTER_WAREHOUSE_DELETED": "删除未使用仓库",
    "MASTER_WAREHOUSE_RENAMED": "仓库更名", "MASTER_LOCATION_DELETED": "删除未使用仓位",
    "PURCHASE_ORDER_BATCH_ISSUED": "合并采购单生成", "SCHEDULE_ORDER_LINKED": "排期关联新订单",
    "SCHEDULE_ORDER_MARK_CHANGED": "排期下单标记变更", "SUPPLIER_MEMBER_CHANGED": "供应商协同成员维护",
    "UNMATCHED_DELIVERY_IMPORT_DELETED": "未匹配送货导入删除", "EXCEPTION_STATUS_UPDATED": "异常状态更新",
    "MASTER_DATA_SAVED": "基础资料维护", "MASTER_LOCATION_UPDATED": "仓位资料维护", "INVENTORY_LOCATION_CREATED": "仓位建档",
    "PURCHASE_ORDER_BASELINE_BACKFILLED": "既有订单供应商历史基线补录",
    "HISTORY_ORDER_PLACED": "历史已下单转待收料", "HISTORY_ORDER_MATERIAL_COMPLETED": "收料补齐历史纸品资料",
    "HISTORY_ORDER_DELETED": "删除历史订单", "ORDER_DELETED": "删除订单", "ORDER_RETURNED": "订单退单",
    "RECEIPT_CREATED": "收料单创建", "RECEIPT_DRAFT_CREATED": "收料草稿创建",
    "RECEIPT_REPLENISHMENT_LINKED": "补货关联补单及计费责任", "RECEIPT_ORDINARY_CLASSIFIED": "收料确认为普通采购",
    "INVENTORY_MOVEMENT_CREATED": "库存流水登记", "INVENTORY_PRICE_CONFIRMED": "入库单价核实", "INVENTORY_LOCATION_CHANGED": "库存调仓",
    "STOCKTAKE_CREATED": "生成盘点单", "STOCKTAKE_SAVE": "盘点草稿保存", "STOCKTAKE_CONFIRM": "盘点确认提交并入账",
    "STOCKTAKE_SUBMIT": "盘点提交复核", "STOCKTAKE_APPROVE": "盘点复核入账", "STOCKTAKE_RETURN": "盘点退回重盘", "STOCKTAKE_CANCEL": "盘点取消",
    "INVENTORY_BULK_OUTBOUND_CREATED": "批量出库", "INVENTORY_MOVEMENT_REVERSED": "库存流水冲销", "HISTORY_INVENTORY_IMPORTED": "历史库存导入",
    "IMPORT_BATCH_CREATED": "导入批次创建", "SCHEDULE_IMPORT_UNDONE": "整批撤销排期导入", "UNMATCHED_DELIVERY_DECIDED": "无单送货核实",
    "CLOSING_GENERATED": "月结草稿生成", "CLOSING_PENDING": "月结提交核对", "CLOSING_CONFIRMED": "月结确认", "CLOSING_LOCKED": "最终锁账", "CLOSING_UNLOCKED": "主管解锁月结",
    "CARTON_MARK_TEMPLATE_CREATED": "唛头模板创建", "CARTON_MARK_TEMPLATE_RECHECKED": "唛头模板复核",
    "ORDER_CREATED": "订单创建确认", "ORDER_SUBMITTED_SUPPLIER": "确认订单并锁定",
    "PURCHASE_ORDER_ISSUED": "供应商采购单生成", "ORDER_UPDATED": "订单修改",
    "ORDER_APPENDED": "追加订单", "ORDER_REDUCED": "订单减单 / 退单", "ORDER_CANCELLED": "订单取消",
    "ORDER_REPLENISHED": "补单并出库", "RECEIPT_CONFIRMED": "收料确认入库", "RECEIPT_REVERSED": "收料作废 / 冲销",
    "CARTON_MARK_ASSET_CREATED": "箱唛原文件上传", "CARTON_MARK_ASSET_BOUND": "箱唛关联订单",
    "CARTON_MARK_ASSET_RESTORED": "箱唛资料恢复", "CARTON_MARK_ASSET_ARCHIVED": "箱唛资料归档",
    "FEEDBACK_CREATED": "员工问题反馈", "FEEDBACK_REPLIED": "管理员回复反馈",
    "FEATURE_UPDATE_PUBLISHED": "发布功能变动", "SUPPLIER_PAPER_ACCEPTED": "供应商纸品接单",
    "SUPPLIER_SHIPMENT_CREATED": "供应商确认发货", "SUPPLIER_SHIPMENT_RECEIVED": "仓库核实收货",
    "SUPPLIER_SHIPMENT_NOT_RECEIVED": "仓库未收到",
    "SUPPLIER_SHIPMENT_RECEIPT_REVERSED": "收料冲销待更正",
    "SUPPLIER_SHIPMENT_LINE_LINKED": "无单纸品关联正式订单",
    "SUPPLIER_DOCUMENT_EXPORTED": "供应商单据导出",
    "SUPPLIER_SETTLEMENT_SAVED": "供应商月结草稿保存",
    "SUPPLIER_SETTLEMENT_CONFIRMED": "双方月结确认",
    "SUPPLIER_SETTLEMENT_REOPENED": "供应商月结重开",
    "SUPPLIER_SETTLEMENT_REVIEWED": "供应商月结核对反馈",
}
