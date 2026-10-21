import type { StatementLine, SupplierSource } from '@/api/cartonSupplierSettlement'
import { dimensionLabel } from './paperCatalog'

export const settlementDateLabel = (source?: SupplierSource) => source?.kind === 'RETURN_REFUND' ? '现金退款到账日期'
  : source?.kind === 'RETURN' ? source.date_basis === 'RETURN_ACTUAL' ? '实际退货日期' : '历史记账日期（实际退货日期待核实）'
    : source?.kind === 'RECEIPT' ? '实际验收日期' : '归属日期'
export const settlementSourceLabel = (source?: SupplierSource) => source?.kind === 'RETURN_REFUND' ? '现金退款（加回应结）'
  : source?.kind === 'RETURN' ? '退货贷项' : source?.kind === 'RECEIPT' ? '收料' : '未关联'
export const settlementAmountDirection = (source?: SupplierSource) => source?.kind === 'RETURN' ? '减少应结'
  : source?.kind === 'RETURN_REFUND' ? '增加应结（已核实现金退款）' : source?.kind === 'RECEIPT' ? '增加应结' : '待核实'
export const settlementSignedAmount = (line: StatementLine, source?: SupplierSource) => line.amount == null ? ''
  : source?.kind === 'RETURN' ? `-${line.amount}` : source?.kind === 'RETURN_REFUND' || source?.kind === 'RECEIPT' ? line.amount : ''

// A CSV cell must remain text even when an identifier starts with an Excel formula character.
const cell = (value: unknown) => {
  const text = value == null ? '' : String(value)
  return `"${(/^(?:\s*[=+\-@]|[\t\r\n]|0\d|\d{16,}$)/.test(text) ? "'" : '') + text.replace(/"/g, '""')}"`
}
export function settlementCsv(lines: StatementLine[], sources: Map<string, SupplierSource>, period: string, currency: string) {
  const rows: unknown[][] = [['月份', '客户', '合同号', '货号', '送货凭证', '收料/退货/资金凭证', '纸品类型', '纸质', '原规格', '原尺寸单位', '验收/退货/到账归属日期', '日期依据', '库存记账日期', '结算数量', '计量单位', '结算单价', '结算金额', '币种', '依据', '来源标识', '应结方向', '本行应结金额']]
  for (const line of lines) {
    const source = sources.get(line.source_key)
    rows.push([period, source?.customer_name, source?.contract_no, source?.item_no, line.document_no,
      settlementSourceLabel(source), source?.packaging_type, source?.paper_quality,
      source?.specification, dimensionLabel(source?.dimension_unit || ''), source?.acceptance_date,
      settlementDateLabel(source), source?.kind === 'RETURN' ? source.posting_date || source.acceptance_date : '',
      line.quantity, source?.unit, line.unit_price, line.amount, currency, line.note, line.source_key,
      settlementAmountDirection(source), settlementSignedAmount(line, source)])
  }
  return '\uFEFF' + rows.map((row, rowIndex) => row.map((value, index) => rowIndex > 0 && index === row.length - 1 && /^-?\d+(?:\.\d+)?$/.test(String(value)) ? `"${value}"` : cell(value)).join(',')).join('\r\n')
}
export function exportSettlementLines(lines: StatementLine[], sources: Map<string, SupplierSource>, period: string, currency: string, scope: string) {
  const blob = new Blob([settlementCsv(lines, sources, period, currency)], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob), anchor = document.createElement('a')
  anchor.href = url; anchor.download = `${period}-${scope === 'CARD' ? '配卡专项' : '纸品'}对账明细-${currency}.csv`
  anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
}
