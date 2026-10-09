import type { CartonExceptionResponse, CartonImportPreviewRow } from '@/api/cartonProcurement'

type ExceptionIdentity = Pick<CartonExceptionResponse, 'contract_no' | 'item_no' | 'customer_name' | 'category' | 'description'>
const identity = (value?: string) => (value ?? '').trim().toLowerCase().replace(/[\s\-_/\\.]/g, '')

/** Request-local index: preserve wildcard and ambiguous-match semantics without rescanning a batch per alert. */
export function weeklyExceptionLookup(rows: CartonImportPreviewRow[]) {
  const normalized = rows.map(row => ({ row, contract: identity(row.contract_no ?? row.reference),
    item: identity(row.item_no), customer: identity(row.customer_name),
    location: JSON.stringify([row.source_sheet, row.source_row, row.source_reference || '未填']) }))
  type Entry = typeof normalized[number]
  const indexes = { contract: new Map<string, Entry[]>(), item: new Map<string, Entry[]>(),
    customer: new Map<string, Entry[]>(), location: new Map<string, Entry[]>() }
  for (const entry of normalized) for (const field of ['contract', 'item', 'customer', 'location'] as const) {
    const bucket = indexes[field].get(entry[field])
    if (bucket) bucket.push(entry)
    else indexes[field].set(entry[field], [entry])
  }
  const cache = new Map<string, CartonImportPreviewRow | null>()
  return (exception: ExceptionIdentity): CartonImportPreviewRow | null => {
    const contract = identity(exception.contract_no), item = identity(exception.item_no)
    const customer = exception.customer_name ? identity(exception.customer_name) : null
    const match = exception.description.match(/\n来源：(.+) · 第 (\d+) 行 · SO：(.*)$/)
    const location = match ? JSON.stringify([match[1], Number(match[2]), match[3]]) : null
    const cancelled = ['SCHEDULE_CANCELLED', 'SCHEDULE_CANCELLED_AFTER_ORDER'].includes(exception.category)
    const key = JSON.stringify([contract, item, customer, location, cancelled])
    if (cache.has(key)) return cache.get(key)!
    let candidates = normalized
    for (const [field, value] of [['contract', contract || null], ['item', item || null], ['customer', customer], ['location', location]] as const) {
      if (value === null) continue
      const bucket = indexes[field].get(value) ?? []
      if (bucket.length < candidates.length) candidates = bucket
    }
    let found: CartonImportPreviewRow | null = null
    for (const entry of candidates) {
      if ((contract && entry.contract !== contract) || (item && entry.item !== item)
        || (customer !== null && entry.customer !== customer) || (location !== null && entry.location !== location)
        || (cancelled && entry.row.schedule_section !== 'CANCELLED')) continue
      if (found) { cache.set(key, null); return null }
      found = entry.row
    }
    cache.set(key, found)
    return found
  }
}
