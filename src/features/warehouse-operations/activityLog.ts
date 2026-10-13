import type { WarehouseDocument } from '@/api/warehouseOperations'
import { operationLabels, qualityLabels } from './operations'

export function operationTime(value: string) {
  if (!value) return ''
  const date = new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value.replace(' ', 'T')}+08:00`)
  return Number.isNaN(date.getTime()) ? '' : new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  }).format(date)
}
export function activityLabel(row: WarehouseDocument) {
  return row.read_only ? '采购实收入库 · 批次' : operationLabels[row.kind]
}
export function activitySummary(row: WarehouseDocument) {
  const data = row.data as typeof row.data & { book_quantity?: string; actual_quantity?: string }
  const place = row.batch_snapshot?.location || '未记录'
  const unit = data.unit || row.batch_snapshot?.unit || ''
  if (row.kind === 'LOCATION_BIND') return `仓位 ${place} → ${data.location || '未记录'}；数量不变`
  if (row.kind === 'TRANSFER') return `${place} → ${data.location || '未记录'}；调仓 ${data.quantity} ${unit}`
  if (row.kind === 'STOCKTAKE') return `账面 ${data.book_quantity ?? '未记录'} → 实盘 ${data.actual_quantity ?? '未记录'} ${unit}；差异 ${data.quantity}`
  if (row.kind === 'CORRECTION') return `冲销${operationLabels[data.reversed_kind || 'RECEIPT'].replace(/^登记/, '')} ${data.quantity} ${unit}；原单保留`
  if (row.kind === 'QUALITY') return `历史质检：${row.batch_snapshot?.quality_status ? qualityLabels[row.batch_snapshot.quality_status] : '未记录'} → ${qualityLabels[data.quality_status] || '未记录'}`
  if (row.kind === 'REQUEST') return `领料申请 ${data.quantity} ${unit}，登记申请不扣库存`
  return `${row.kind === 'ISSUE' ? '发出' : row.kind === 'RETURN' ? '退回' : row.kind === 'OPENING' ? '建立期初' : '实收'} ${data.quantity} ${unit}${data.location ? ` · ${data.location}` : ''}`
}

export interface ActivityFilters { search: string; from: string; to: string; kind: string; actor: string; state: string; dateField: 'OPERATION' | 'BUSINESS'; sort: 'DESC' | 'ASC' }
export function filterActivity(rows: WarehouseDocument[], filters: ActivityFilters) {
  if (filters.from && filters.to && filters.from > filters.to) return []
  const day = (row: WarehouseDocument) => filters.dateField === 'BUSINESS' ? row.business_date : operationTime(row.occurred_at).slice(0, 10)
  const query = filters.search.trim().toLocaleLowerCase()
  return rows.filter(row => (!filters.kind || row.kind === filters.kind) && (!filters.actor || row.actor_name === filters.actor)
    && (!filters.state || Boolean(row.reversed) === (filters.state === 'REVERSED'))
    && (!filters.from || !!day(row) && day(row) >= filters.from) && (!filters.to || !!day(row) && day(row) <= filters.to)
    && (!query || [JSON.stringify(row), activityLabel(row), activitySummary(row)].join(' ').toLocaleLowerCase().includes(query)))
    .sort((a, b) => {
      const at = filters.dateField === 'BUSINESS' ? a.business_date : operationTime(a.occurred_at)
      const bt = filters.dateField === 'BUSINESS' ? b.business_date : operationTime(b.occurred_at)
      if (!at || !bt) return at ? -1 : bt ? 1 : a.id.localeCompare(b.id)
      return (bt.localeCompare(at) || b.sequence - a.sequence || b.id.localeCompare(a.id)) * (filters.sort === 'ASC' ? -1 : 1)
    })
}
