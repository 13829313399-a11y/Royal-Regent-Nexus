import type { SupplierDocument, SupplierDocumentLine } from '@/api/cartonSupplierPortal'

export interface DeliveryNoteContext {
  supplierName: string
  factoryName: string
}

const escape = (value: unknown) => String(value ?? '').replace(/[&<>"']/g, character => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character] ?? character))

function lineLabel(line: SupplierDocumentLine) {
  return line.child_no || `无单纸品 · ${line.contract_no || '无合同号'} / ${line.item_no || '无货号'}`
}

function quantityTotals(lines: SupplierDocumentLine[]) {
  const byUnit = new Map<string, number>()
  for (const line of lines) {
    const quantity = Number(line.quantity)
    if (!Number.isFinite(quantity)) continue
    byUnit.set(line.unit || '', (byUnit.get(line.unit || '') ?? 0) + quantity)
  }
  return [...byUnit].map(([unit, total]) => `${total.toLocaleString('zh-CN', { maximumFractionDigits: 4 })}${unit ? ' ' + unit : ''}`).join(' / ')
}

/** Standalone printable delivery note: no application chrome, A4 friendly. */
export function deliveryNoteHtml(document: SupplierDocument, context: DeliveryNoteContext): string {
  const lines = document.lines ?? []
  const rows = lines.map((line, index) => `<tr>
    <td class="index">${index + 1}</td>
    <td>${escape(line.customer_name || '—')}</td>
    <td>${escape(line.order_no || '—')}<br><span class="muted">${escape(lineLabel(line))}</span></td>
    <td>${escape(line.packaging_type || '—')}</td>
    <td>${escape(line.paper_quality || '—')}<br><span class="muted">${escape(line.specification || '规格待补')}</span></td>
    <td class="number">${escape(line.quantity)}</td>
    <td>${escape(line.unit)}</td>
  </tr>`).join('')
  return `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>送货单 ${escape(document.document_no)}</title>
<style>
  @page { size: A4; margin: 12mm; }
  * { box-sizing: border-box; }
  body { margin: 0; color: #111827; font-family: "Microsoft YaHei", "PingFang SC", sans-serif; font-size: 12px; }
  h1 { margin: 0; font-size: 22px; letter-spacing: 6px; text-align: center; }
  .meta { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 24px; margin: 14px 0 10px; }
  .meta span { color: #4b5563; }
  table { width: 100%; border-collapse: collapse; }
  th, td { border: 1px solid #9ca3af; padding: 6px 8px; text-align: left; vertical-align: top; }
  th { background: #f3f4f6; font-size: 11px; }
  td.number { text-align: right; white-space: nowrap; }
  td.index { width: 34px; text-align: center; }
  .muted { color: #6b7280; font-size: 10px; }
  .totals { margin-top: 8px; text-align: right; font-weight: 700; }
  .sign { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 24px; margin-top: 44px; }
  .sign div { border-top: 1px solid #6b7280; padding-top: 6px; color: #4b5563; }
  .foot { margin-top: 18px; color: #6b7280; font-size: 10px; }
</style></head>
<body>
  <h1>送 货 单</h1>
  <div class="meta">
    <div><span>供应商：</span>${escape(context.supplierName || '—')}</div>
    <div><span>收货厂区：</span>${escape(context.factoryName || '—')}</div>
    <div><span>单据号：</span>${escape(document.document_no)}</div>
    <div><span>送货日期：</span>${escape(document.date || '—')}</div>
    <div><span>订单数：</span>${document.orders?.length ?? 0} 张</div>
    <div><span>纸品行数：</span>${lines.length} 行</div>
  </div>
  <table>
    <thead><tr><th>#</th><th>客户</th><th>订单 / 纸品</th><th>纸品类型</th><th>纸质 / 规格</th><th>数量</th><th>单位</th></tr></thead>
    <tbody>${rows || '<tr><td colspan="7" style="text-align:center;color:#6b7280">本单没有纸品明细</td></tr>'}</tbody>
  </table>
  <div class="totals">合计：${escape(quantityTotals(lines) || '0')}</div>
  <div class="sign"><div>供应商签章</div><div>仓库签收</div><div>签收日期</div></div>
  <p class="foot">本单由纸箱供应商协同系统生成，仅作送货与签收凭证；实际入库数量以仓库验收为准。</p>
</body></html>`
}
