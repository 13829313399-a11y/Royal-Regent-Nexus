import type { StatementLine, SupplierSource } from '@/api/cartonSupplierSettlement'
import { dimensionLabel } from './paperCatalog'

// A CSV cell must remain text even when an identifier starts with an Excel formula character.
const cell = (value: unknown) => {
  const text = value == null ? '' : String(value)
  return `"${(/^(?:\s*[=+\-@]|[\t\r\n]|0\d|\d{16,}$)/.test(text) ? "'" : '') + text.replace(/"/g, '""')}"`
}
export function settlementCsv(lines: StatementLine[], sources: Map<string, SupplierSource>, period: string, currency: string) {
  const rows: unknown[][] = [['月份', '客户', '合同号', '货号', '送货凭证', '收料/退货', '纸品类型', '纸质', '原规格', '原尺寸单位', '实际验收日期', '结算数量', '计量单位', '结算单价', '结算金额', '币种', '依据', '来源标识']]
  for (const line of lines) {
    const source = sources.get(line.source_key)
    rows.push([period, source?.customer_name, source?.contract_no, source?.item_no, line.document_no,
      source?.kind === 'RETURN' ? '退货' : source ? '收料' : '未关联', source?.packaging_type, source?.paper_quality,
      source?.specification, dimensionLabel(source?.dimension_unit || ''), source?.acceptance_date,
      line.quantity, source?.unit, line.unit_price, line.amount, currency, line.note, line.source_key])
  }
  return '\uFEFF' + rows.map(row => row.map(cell).join(',')).join('\r\n')
}
export function exportSettlementLines(lines: StatementLine[], sources: Map<string, SupplierSource>, period: string, currency: string, scope: string) {
  const blob = new Blob([settlementCsv(lines, sources, period, currency)], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob), anchor = document.createElement('a')
  anchor.href = url; anchor.download = `${period}-${scope === 'CARD' ? '配卡专项' : '纸品'}对账明细-${currency}.csv`
  anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
}
