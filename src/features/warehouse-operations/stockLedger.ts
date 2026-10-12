import type { WarehouseBatch } from '@/api/warehouseOperations'
import { remaining } from './operations'

export type StockState = 'IN_STOCK' | 'AVAILABLE' | 'UNVERIFIED' | 'RESTRICTED' | 'EMPTY' | 'ALL'
export type StockSort = 'DEFAULT' | 'ITEM' | 'LOCATION' | 'DATE_DESC' | 'DATE_ASC' | 'QUANTITY_ASC' | 'QUANTITY_DESC'
export const stockLocationKey = (row: WarehouseBatch) => row.location_id || `unverified:${row.location}`
export const stockRestricted = (row: WarehouseBatch) => row.quality_status === 'HOLD' || row.quality_status === 'REJECTED'
export function stockStateMatches(row: WarehouseBatch, state: StockState) {
  const positive = Number(row.quantity) > 0
  switch (state) {
    case 'IN_STOCK': return positive
    case 'AVAILABLE': return positive && !!row.location_verified && !stockRestricted(row)
    case 'UNVERIFIED': return positive && !row.location_verified
    case 'RESTRICTED': return positive && stockRestricted(row)
    case 'EMPTY': return !positive
    default: return true
  }
}
const natural = (a: string, b: string) => a.localeCompare(b, 'zh-CN', { numeric: true })
export function sortStockRows(rows: WarehouseBatch[], sort: StockSort): WarehouseBatch[] {
  if (sort === 'DEFAULT') return rows
  return [...rows].sort((a, b) => {
    let result = 0
    if (sort === 'ITEM') result = natural(a.item_code, b.item_code) || natural(a.item_name, b.item_name)
    if (sort === 'LOCATION') result = natural(a.warehouse_name || '', b.warehouse_name || '') || natural(a.location_label || a.location, b.location_label || b.location)
    if (sort === 'DATE_ASC' || sort === 'DATE_DESC') {
      if (!a.received_on || !b.received_on) result = a.received_on ? -1 : b.received_on ? 1 : 0
      else result = a.received_on.localeCompare(b.received_on) * (sort === 'DATE_ASC' ? 1 : -1)
    }
    if (sort === 'QUANTITY_ASC' || sort === 'QUANTITY_DESC') {
      // Different units are grouped, never interpreted as comparable physical quantities.
      result = natural(a.unit, b.unit)
      if (!result) {
        const difference = remaining(a.quantity, b.quantity)
        const comparison = /^-/.test(difference) ? -1 : /[1-9]/.test(difference) ? 1 : 0
        result = comparison * (sort === 'QUANTITY_ASC' ? 1 : -1)
      }
    }
    return result || natural(a.id, b.id)
  })
}
