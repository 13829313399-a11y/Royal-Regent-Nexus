import type { SpecialRequest } from '@/api/cartonSpecialRequests'

export type SpecialAdjustmentAction = 'adjust' | 'append' | 'reduce' | 'date' | 'material'
export type SpecialOrderAction = SpecialAdjustmentAction | 'purchase' | 'receive' | 'edit' | 'confirm' | 'cancel' | 'delete' | 'copy' | 'return-stock' | 'replenish' | 'undo-replenish'

export const specialAdjustmentCopy: Record<SpecialAdjustmentAction, { title: string; help: string }> = {
  adjust: { title: '调整订单', help: '填写调整后的总需求、需用日期及未送货纸品资料，原版本与已收批次保留。' },
  append: { title: '追加订单', help: '填写调整后的总需求，不是本次追加量。例如原需求 100、增加 20，应填 120。' },
  reduce: { title: '减少未入库量', help: '填写调整后的总需求，不是本次减少量。例如原需求 100、减少 20，应填 80；不能少于累计有效入库数量。' },
  date: { title: '调整交期', help: '仅修改需用日期，保留原纸品和数量；保存后沿当前需求版本发布调整，历史日期记录保留。' },
  material: { title: '修改未送货纸品', help: '核对未送货纸品的类型、纸质、规格和单位；已送货纸品身份与计数单位保持原样。' },
}

export function isSpecialAdjustmentAction(action?: SpecialOrderAction): action is SpecialAdjustmentAction {
  return Boolean(action && ['adjust', 'append', 'reduce', 'date', 'material'].includes(action))
}

export function canAdjustSpecialRequest(request: SpecialRequest) {
  return !request.deleted && request.permissions.can_adjust === true
    && ['SAMPLE', 'WORKSHOP_MISC'].includes(request.kind) && !['SUPPLIER_EXTRA', 'REPLENISHMENT'].includes(request.origin || '') && !request.replacement
    && ['SENT', 'QUOTED', 'READY', 'PARTIALLY_RECEIVED'].includes(request.status)
}

export function canAppendSpecialRequest(request: SpecialRequest) {
  return (canAdjustSpecialRequest(request) && request.permissions.can_append !== false) || (!request.deleted && request.status === 'COMPLETED'
    && request.permissions.can_append === true && ['SAMPLE', 'WORKSHOP_MISC'].includes(request.kind)
    && !['SUPPLIER_EXTRA', 'REPLENISHMENT'].includes(request.origin || '') && !request.replacement)
}
