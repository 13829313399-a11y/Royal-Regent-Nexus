import type { WarehouseDocument } from '@/api/warehouseOperations'

function csvField(value: string | undefined): string {
  const text = value ?? ''
  return /[,"\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

/** Export the supplied order and recorded values without changing or totaling documents. */
export function fabricIssueCsv(rows: WarehouseDocument[]): string {
  const header = ['业务日期', '单据编号', '放产单号', '领用方', '物料编码', '物料名称/规格', '缸号', '卷号', '仓位', '单位', '数量', '用途/备注', '经办人', '状态']
  const lines = rows.filter(row => row.kind === 'ISSUE').map(row => {
    const { data, batch_snapshot: batch } = row
    return [row.business_date, row.id, data?.production_no, data?.counterparty,
      data?.item_code || batch?.item_code, data?.item_name || batch?.item_name, data?.lot || batch?.lot,
      data?.roll_no || batch?.roll_no, data?.location || batch?.location, data?.unit || batch?.unit,
      data?.quantity, [data?.purpose, data?.reason].filter(Boolean).join(' / '), row.actor_name,
      row.reversed ? '已冲销' : '已登记'].map(csvField).join(',')
  })
  return [header.join(','), ...lines].join('\r\n')
}
