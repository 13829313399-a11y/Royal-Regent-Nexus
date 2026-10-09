import { describe, expect, it } from 'vitest'
import { reactive } from 'vue'
import { weeklyExceptionLookup } from '../cartonAlertIndex'
import type { CartonImportPreviewRow } from '@/api/cartonProcurement'

const norm = (v?: string) => (v ?? '').trim().toLowerCase().replace(/[\s\-_/\\.]/g, '')
type Identity = Parameters<ReturnType<typeof weeklyExceptionLookup>>[0]
function legacy(rows: CartonImportPreviewRow[], e: Identity) {
  const location = e.description.match(/\n来源：(.+) · 第 (\d+) 行 · SO：(.*)$/)
  const matches = rows.filter(r => (!norm(e.contract_no) || norm(r.contract_no ?? r.reference) === norm(e.contract_no))
    && (!norm(e.item_no) || norm(r.item_no) === norm(e.item_no))
    && (!e.customer_name || norm(r.customer_name) === norm(e.customer_name))
    && (!['SCHEDULE_CANCELLED', 'SCHEDULE_CANCELLED_AFTER_ORDER'].includes(e.category) || r.schedule_section === 'CANCELLED')
    && (!location || (r.source_sheet === location[1] && r.source_row === Number(location[2]) && (r.source_reference || '未填') === location[3])))
  return matches.length === 1 ? matches[0] ?? null : null
}
const exception = (fields: Partial<Identity> = {}): Identity => ({ contract_no: '', item_no: '', customer_name: '', category: 'MISSING_ORDER', description: '', ...fields })

describe('indexed dashboard source association', () => {
  it('preserves wildcards, punctuation, source coordinates, cancellation and ambiguity', () => {
    const rows: CartonImportPreviewRow[] = [
      { contract_no: ' A-1 ', item_no: 'I_1', customer_name: ' 客 户 ', source_sheet: 'ITEM', source_row: 2, source_reference: 'SO1', schedule_section: 'PENDING' },
      { contract_no: 'A1', item_no: 'I1', customer_name: '客户', source_sheet: 'ITEM', source_row: 3, source_reference: 'SO2', schedule_section: 'CANCELLED' },
      { reference: 'B1', item_no: 'I2', customer_name: '', source_sheet: 'ITEM', source_row: 4 },
    ]
    const lookup = weeklyExceptionLookup(rows)
    for (const contract_no of ['', 'a1', 'B1', 'missing']) for (const item_no of ['', 'I1', 'I2'])
      for (const customer_name of ['', '客户', ' ']) for (const category of ['MISSING_ORDER', 'SCHEDULE_CANCELLED'])
        for (const description of ['', '\n来源：ITEM · 第 2 行 · SO：SO1', '\n来源：ITEM · 第 4 行 · SO：未填']) {
          const e = exception({ contract_no, item_no, customer_name, category, description })
          expect(lookup(e)).toBe(legacy(rows, e))
        }
    expect(lookup(exception({ contract_no: 'a1' }))).toBeNull()
    expect(weeklyExceptionLookup([rows[0]!, { ...rows[0]! }])(exception({ contract_no: 'a1' }))).toBeNull()
  })

  it('keeps 5000 reactive rows bounded and does not share matches across batches', () => {
    let reads = 0
    const rows = reactive(Array.from({ length: 5000 }, (_, i) => ({
      get contract_no() { reads++; return `C${i}` }, item_no: `I${i}`, customer_name: 'TEST', source_row: i,
    })))
    const lookup = weeklyExceptionLookup(rows)
    for (let i = 0; i < rows.length; i++) expect(lookup(exception({ contract_no: `C${i}`, item_no: `I${i}` }))).toBe(rows[i])
    // Count actual source reads rather than asserting fragile wall-clock thresholds.
    expect(reads).toBeLessThan(15000)
    const differentBatch = [{ contract_no: 'C0', item_no: 'I0', customer_name: 'TEST' }]
    expect(weeklyExceptionLookup(differentBatch)(exception({ contract_no: 'C0' }))).toBe(differentBatch[0])
  })
})
