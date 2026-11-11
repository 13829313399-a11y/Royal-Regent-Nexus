import type { CartonExceptionResponse } from '@/api/cartonProcurement'

const sources: Record<string, { label: string; action: string; guidance: string }> = {
  WEEKLY_SCHEDULE: { label: '业务下单排期', action: '打开原排期', guidance: '核对原排期与正式订单，在排期页完成对应处理后记录结论。' },
  INSPECTION_SCHEDULE: { label: '查货排期', action: '打开原查货排期', guidance: '核对验货日期、对应订单和供应商交期，按实际跟进结果记录结论。' },
  DELIVERY_NOTE: { label: '历史送货导入', action: '查看原导入凭证', guidance: '核对原送货单与订单纸品，实际验收或更正请到收料入库办理。' },
  ORDER: { label: '正式采购订单', action: '定位原订单', guidance: '在订单台账核对追加后的纸品数量和采购版本，再记录仓库复核结果。' },
  STOCKTAKE: { label: '库存盘点单', action: '查看原盘点单', guidance: '由有主管调整权限的人员核对仓位差额与入账记录，并填写抽查或复核结论。' },
}

const guidanceByCategory: Record<string, string> = {
  MISSING_ORDER: '在原排期核实客户、合同和货号，按实际情况关联已有订单或下单。',
  SCHEDULE_NEW_ORDER: '在原排期核实新增需求与已有订单，完成关联或下单后记录结果。',
  SCHEDULE_CANCELLED: '在原排期核实退单来源和是否已有采购，再记录核对结果。',
  SCHEDULE_CANCELLED_AFTER_ORDER: '核对原排期与已发采购。确认停单需要到原订单办理并跟进供应商回执。',
  QUANTITY_MISMATCH: '核对原单与正式采购的数量和单位，需要调整时在对应业务单据办理。',
  SCHEDULE_DATE_MISMATCH: '核对业务走货期和订单客户交期，需要改期时在原订单办理。',
  AMBIGUOUS_MATCH: '用客户、合同、货号和纸品明细核对候选订单，确认唯一来源后再处理。',
  INSPECTION_ORDER_MISSING: '根据原查货排期核实客户、合同与货号，确认是否漏单并跟进下单。',
  INSPECTION_ORDER_AMBIGUOUS: '在原查货排期核对候选订单和纸品，确认具体来源。',
  INSPECTION_DATE_INVALID: '向排期来源确认验货日期，并在查货排期重新核对交货提醒。',
  INSPECTION_DELIVERY_OVERDUE: '核对最迟交货日和实际收料，跟进供应商未交数量与交期。',
  INSPECTION_DELIVERY_DUE: '核对最迟交货日与供应商承诺，跟进待交纸品。',
  INSPECTION_DELIVERY_REMINDER: '核对查货窗口和待交纸品，按需要跟进供应商交期。',
}

export function exceptionGuide(record: Pick<CartonExceptionResponse, 'source_type' | 'category' | 'source_id'>) {
  const source = Object.hasOwn(sources, record.source_type) ? sources[record.source_type] : undefined
  return {
    label: source?.label ?? '历史异常记录',
    action: record.source_id ? source?.action ?? '' : '',
    guidance: (Object.hasOwn(guidanceByCategory, record.category) ? guidanceByCategory[record.category] : undefined)
      ?? source?.guidance ?? '核对异常说明和留存凭证，再记录处理结论。',
  }
}
