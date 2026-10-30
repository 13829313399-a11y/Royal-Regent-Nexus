import type { SpecialLine, UnifiedOrderEntry } from '@/api/cartonSpecialRequests'
import type { AppendItem } from '@/api/cartonBatchOrders'
import { shallowReactive } from 'vue'

// Exact four-place decimal arithmetic; never round demand through a JS float.
export function scaledQuantity(value: string): bigint | null {
  const match = /^(\d{1,14})(?:\.(\d{1,4}))?$/.exec(value.trim())
  return match ? BigInt(match[1]!) * 10000n + BigInt((match[2] || '').padEnd(4, '0')) : null
}
export function sumQuantity(before: string, delta: string): string {
  const a = scaledQuantity(before), b = scaledQuantity(delta || '0')
  if (a === null || b === null || a + b > 999999999999999999n) return '数量无效'
  const result = a + b
  return `${result / 10000n}.${String(result % 10000n).padStart(4, '0')}`.replace(/\.?0+$/, '') || '0'
}
export interface AppendDraft {
  entry: UnifiedOrderEntry; key: string; number: string; contract: string; item: string; date: string; dateLabel: string
  reason: string; due_date: string; removed: boolean; new_lines: SpecialLine[]
  lines: { id: string; label: string; unit: string; current: string; addition: string }[]
}
export function appendDraft(entry: UnifiedOrderEntry): AppendDraft {
  const regular = entry.order, special = entry.special
  if (!regular && !special) throw new Error('订单资料不完整')
  return {
    entry, key: `${entry.kind}:${regular?.order_no || special!.id}`, number: regular?.order_no || special!.request_no,
    contract: regular?.contract_no || '', item: regular?.item_no || '',
    date: (regular?.quantity_basis === 'CALCULATED' && regular.customer_due_date ? regular.customer_due_date : regular?.due_date) || special?.required_date || '',
    dateLabel: regular ? regular.quantity_basis === 'CALCULATED' && regular.customer_due_date ? '客户交期' : '计划交期' : '需用日期',
    reason: '', due_date: '', removed: false, new_lines: [],
    lines: regular ? regular.lines.map(line => ({ id: line.id, label: [regular.item_no, line.packaging_type, line.paper_quality, line.specification, line.dimension_unit].filter(Boolean).join(' · '), unit: line.unit, current: String(line.required_quantity), addition: '' }))
      : special!.lines.map(line => ({ id: line.id!, label: [line.item_no, line.packaging_type, line.paper_quality, line.specification, line.dimension_unit].filter(Boolean).join(' · '), unit: line.unit, current: line.quantity, addition: '' })),
  }
}
export function appendItems(drafts: AppendDraft[], commonReason: string): AppendItem[] {
  return drafts.filter(row => !row.removed).flatMap(row => {
    const lines = row.lines.flatMap(line => {
      const value = scaledQuantity(line.addition || '0')
      if (value === null || sumQuantity(line.current, line.addition) === '数量无效') throw new Error(`${row.number}：追加数量须为非负数，最多四位小数`)
      return value > 0n ? [{ id: line.id, additional_quantity: line.addition.trim() }] : []
    })
    if (!lines.length && !row.new_lines.length) return []
    const reason = (row.reason || commonReason).trim()
    if (reason.length < 4 || reason.length > 500) throw new Error(`${row.number}：请填写 4–500 字的追加原因`)
    for (const paper of row.new_lines) {
      if (!paper.packaging_type.trim() || !paper.paper_quality.trim() || !paper.specification.trim() || !paper.unit.trim() || (scaledQuantity(paper.quantity) ?? 0n) <= 0n)
        throw new Error(`${row.number}：请补齐新增纸品资料和正数数量`)
    }
    if (row.lines.length + row.new_lines.length > 50) throw new Error(`${row.number}：每张订单最多 50 项纸品`)
    return [{ kind: row.entry.kind, id: row.entry.order?.order_no || row.entry.special!.id,
      expected_revision: row.entry.order?.revision ?? row.entry.special!.revision,
      reason, ...(row.due_date ? { due_date: row.due_date } : {}), lines, new_lines: row.new_lines.map(line => ({ ...line })) }]
  })
}

// Retain uncertain commands across dialog close and authorization refresh. Keys
// are bound to actor/employment/factory, not to the mutable selection or authz revision.
export const pendingCartonBatches = shallowReactive(new Map<string, { body: unknown; file?: File; uncertain: boolean; appendPreview?: AppendDraft[]; commonReason?: string }>())
