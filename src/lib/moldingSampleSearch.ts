import { resolveMaterialComponents } from '@/lib/moldingSampleBusiness'
import type { MoldingSampleWorkflowRecord } from '@/types/moldingSample'

export function normalizeMoldingSampleSearchValue(value: unknown) {
  return String(value ?? '')
    .normalize('NFKC')
    .toLocaleLowerCase('zh-CN')
    .replace(/[\s\p{P}\p{S}]+/gu, '')
}

export function tokenizeMoldingSampleSearchKeyword(keyword: string) {
  return String(keyword ?? '')
    .normalize('NFKC')
    .trim()
    .split(/\s+/u)
    .map((part) => normalizeMoldingSampleSearchValue(part))
    .filter(Boolean)
}

export function buildMoldingSampleSearchValues(record: MoldingSampleWorkflowRecord) {
  const order = record.order
  const values: unknown[] = [
    order.id,
    order.order_number,
    order.doc_number,
    order.product_name,
    order.client_name,
    order.date,
    order.stage,
    order.order_type,
    order.workshop,
    order.send_to,
    order.supervisor,
    order.eng_name,
    order.reason,
    order.status,
    order.reject_reason,
    order.completed_date,
  ]

  for (const item of record.items) {
    values.push(
      item.id,
      item.order_id,
      item.mold_id,
      item.mold_name,
      item.mold_dimensions,
      item.mold_presence_status,
      item.mold_presence_status === 'in_factory' ? '在厂' : item.mold_presence_status === 'out_of_factory' ? '不在厂' : '待确认',
      item.machine_type,
      item.production_machine,
      item.material,
      item.material_usage_type,
      item.material_usage_type === 'trial' ? '试料' : '正式生产',
      item.color,
      item.pigment_no,
      item.quantity,
      item.shoot_qty,
      item.required_material_kg,
      item.mold_return_time,
      item.completion_time,
      item.notes,
      item.receipt_no,
    )

    for (const component of resolveMaterialComponents(item)) {
      values.push(
        component.material,
        component.source_type,
        component.source_type === 'runner' ? '水口料' : '原料',
        component.ratio_percent,
      )
    }
  }

  for (const requisition of record.requisitions ?? []) {
    values.push(
      requisition.id,
      requisition.req_number,
      requisition.order_number,
      requisition.material,
      requisition.applicant,
      requisition.notes,
      requisition.inventory_batch_no,
      requisition.status,
    )
  }

  for (const problem of record.problems ?? []) {
    values.push(
      problem.id,
      problem.order_number,
      problem.description,
      problem.reported_by,
      problem.status,
    )
  }

  return values
    .map((value) => normalizeMoldingSampleSearchValue(value))
    .filter(Boolean)
}

export function matchesMoldingSampleSearch(record: MoldingSampleWorkflowRecord, tokens: string[]) {
  if (!tokens.length) {
    return true
  }

  const searchValues = buildMoldingSampleSearchValues(record)
  return tokens.every((token) => searchValues.some((value) => value.includes(token)))
}
