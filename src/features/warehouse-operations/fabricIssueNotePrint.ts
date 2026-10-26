import type { WarehouseDocument } from '@/api/warehouseOperations'

const escape = (value: unknown) => String(value ?? '').replace(/[&<>"']/g, character => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character] ?? character))
const field = (value: unknown) => escape(value == null || String(value).trim() === '' ? '—' : value)

/** Print only the issue's recorded facts; allocations do not add to the physical quantity. */
export function fabricIssueNoteHtml(document: WarehouseDocument, context: { factoryName?: string }): string {
  const { data, batch_snapshot: batch } = document
  const allocations = data.allocations ?? []
  const allocationTable = allocations.length ? `<section class="allocations">
    <h2>放产单分配</h2>
    <p>分配仅供核对，总数量以本次实发为准</p>
    <table><thead><tr><th scope="col">放产单号</th><th scope="col">分配数量</th></tr></thead>
      <tbody>${allocations.map(row => `<tr><td>${field(row.production_no)}</td><td class="number">${field(row.quantity)}</td></tr>`).join('')}</tbody>
    </table>
  </section>` : ''
  return `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>发料单 ${field(document.id)}</title>
<style>
  @page { size: A4 portrait; margin: 12mm; }
  * { box-sizing: border-box; }
  body { margin: 0; color: #111827; background: white; font-family: "Microsoft YaHei", "Noto Sans CJK SC", "PingFang SC", Arial, sans-serif; font-size: 10pt; line-height: 1.6; }
  .sheet { max-width: 186mm; margin: 0 auto; }
  h1 { margin: 0; font-size: 22pt; letter-spacing: 4pt; text-align: center; }
  .company { margin: 0 0 3mm; font-size: 13pt; font-weight: 700; text-align: center; }
  .meta { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 2mm 6mm; margin: 6mm 0 4mm; }
  .meta span { color: #4b5563; }
  .company, .meta > div, th, td, .sign > div { overflow-wrap: anywhere; white-space: pre-wrap; }
  table { width: 100%; table-layout: fixed; border-collapse: collapse; }
  thead { display: table-header-group; }
  tr { break-inside: avoid; }
  th, td { border: 0.25mm solid #6b7280; padding: 2mm; text-align: left; vertical-align: top; }
  th { background: #f3f4f6; font-size: 9pt; }
  .number { text-align: right; font-variant-numeric: tabular-nums; }
  .muted { color: #4b5563; font-size: 9pt; }
  .allocations { margin-top: 6mm; }
  h2 { margin: 0; font-size: 12pt; break-after: avoid; }
  .allocations p { margin: 1mm 0 3mm; font-size: 9pt; break-after: avoid; }
  .reversed { margin: 4mm 0; border: 0.5mm solid #b91c1c; padding: 2mm; color: #b91c1c; font-size: 16pt; font-weight: 700; text-align: center; print-color-adjust: exact; -webkit-print-color-adjust: exact; }
  footer { break-inside: avoid; }
  .sign { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6mm; margin-top: 14mm; }
  .sign > div { border-top: 0.25mm solid #6b7280; padding-top: 2mm; }
  .foot { margin: 5mm 0 0; font-size: 9pt; color: #4b5563; }
</style></head>
<body><main class="sheet">
  <p class="company">${escape(context.factoryName?.trim() || '华康塑胶制品（东源）有限公司')}</p>
  <h1>发料单</h1>
  ${document.reversed ? '<div class="reversed">已冲销，仅供存档</div>' : ''}
  <div class="meta">
    <div><span>发料单号：</span>${field(document.id)}</div>
    <div><span>业务日期：</span>${field(document.business_date)}</div>
    <div><span>领用方：</span>${field(data.counterparty)}</div>
    <div><span>放产单号：</span>${field(data.production_no)}</div>
    <div><span>用途：</span>${field(data.purpose)}</div>
    <div><span>经办人：</span>${field(document.actor_name)}</div>
  </div>
  <table class="items">
    <colgroup><col style="width:14%"><col style="width:23%"><col style="width:16%"><col style="width:14%"><col style="width:7%"><col style="width:12%"><col style="width:14%"></colgroup>
    <thead><tr><th scope="col">物料编码</th><th scope="col">物料名称/规格</th><th scope="col">缸号/卷号</th><th scope="col">仓位</th><th scope="col">单位</th><th scope="col">数量</th><th scope="col">备注</th></tr></thead>
    <tbody><tr>
      <td>${field(data.item_code || batch?.item_code)}</td>
      <td>${field(data.item_name || batch?.item_name)}${batch?.material_detail ? `<br><span class="muted">${field(batch.material_detail)}</span>` : ''}</td>
      <td>${field(data.lot || batch?.lot)} / ${field(data.roll_no || batch?.roll_no)}</td>
      <td>${field(data.location || batch?.location)}</td>
      <td>${field(data.unit || batch?.unit)}</td>
      <td class="number">${field(data.quantity)}</td>
      <td>${field(data.reason)}</td>
    </tr></tbody>
  </table>
  ${allocationTable}
  <footer>
    <div class="sign"><div>发料人：${field(document.actor_name)}</div><div>领料人：</div><div>日期：</div></div>
    <p class="foot">本单为仓库发料凭证，实际领用以签收为准</p>
  </footer>
</main></body></html>`
}
