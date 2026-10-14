import type { HandoverData } from '@/api/materialHandover'

export interface HandoverReviewIssue { label: string; fields: string[] }

// Drafts may be incomplete. These requirements apply only to confirmation/printing.
export function handoverReviewIssues(data: HandoverData): HandoverReviewIssue[] {
  const issues: HandoverReviewIssue[] = []
  const missing = (value: string | null | undefined) => !value?.trim()
  for (const [value, label] of [[data.source_no, '原单号'], [data.document_date, '单据日期'], [data.counterparty, '制单方']] as const) {
    if (missing(value)) issues.push({ label: `缺少${label}`, fields: [label] })
  }
  if (data.kind === 'DELIVERY' && missing(data.supplier_id)) issues.push({ label: '供应商尚未关联，请仓库选择供应商基础资料', fields: ['制单供应商'] })
  if (!data.lines.length) issues.push({ label: '尚无物料明细，请添加明细或交仓库按原件补录', fields: [] })
  const validNumber = (value: string, allowZero = false) => {
    const text = value.trim(), integer = text.split('.')[0]!.replace(/^0+/, '')
    return /^\d+(\.\d{1,6})?$/.test(text) && text.length <= 32 && integer.length <= 12 && (allowZero || /[1-9]/.test(text))
  }
  data.lines.forEach((line, index) => {
    const fields: string[] = [], messages: string[] = []
    for (const [value, label] of [[line.item_code, '物料编码'], [line.item_name, '物料名称'], [line.unit, '单位']] as const) {
      if (missing(value)) { messages.push(`缺少${label}`); fields.push(`第${index + 1}行${label}`) }
    }
    if (!validNumber(line.quantity)) {
      messages.push(missing(line.quantity) ? '缺少数量' : '数量须大于 0、小于一万亿，最多 6 位小数')
      fields.push(`第${index + 1}行单据数量`)
    }
    if (line.unit_price?.trim() && !validNumber(line.unit_price, true)) {
      messages.push('参考单价须为非负数、小于一万亿，最多 6 位小数；不清楚可留空')
      fields.push(`第${index + 1}行参考单价`)
    }
    if (messages.length) issues.push({ label: `第 ${index + 1} 行${line.item_name.trim() ? `（${line.item_name.trim()}）` : ''}：${messages.join('；')}`, fields })
  })
  return issues
}
