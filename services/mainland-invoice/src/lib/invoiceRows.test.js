import { describe, expect, it } from 'vitest'
import * as XLSX from 'xlsx'
import { invoiceRows } from './invoiceRows.js'
import { computeHkbLedgerFills, fillHkbLedgerWorkbook, HKB_LEDGER_SHEETS } from './hkbLedger.js'

describe('Excel serial compatibility and selected ledger sheets', () => {
  it('keeps date serials and formula caches without altering formats', () => {
    const sheet = XLSX.utils.aoa_to_sheet([[46112, 12.5, '原文本']])
    sheet.A1.z = 'yyyy/m/d;@'
    sheet.B1.f = 'SUM(1,11.5)'
    const before = structuredClone(sheet)
    expect(invoiceRows(sheet)).toEqual([[46112, 12.5, '原文本']])
    expect(sheet).toEqual(before)
  })
  it('also handles dense worksheets and a missing sheet', () => {
    const sheet = XLSX.utils.aoa_to_sheet([[46112]], { dense: true })
    sheet['!data'][0][0].z = 'yyyy/m/d'
    expect(invoiceRows(sheet)).toEqual([[46112]])
    expect(sheet['!data'][0][0].z).toBe('yyyy/m/d')
    expect(invoiceRows(undefined)).toEqual([])
  })
  it('fills only selected B ledger sheets, leaving other sheets unchanged', () => {
    const book = XLSX.utils.book_new()
    for (const name of HKB_LEDGER_SHEETS) {
      const sheet = XLSX.utils.aoa_to_sheet([['2026年1月份'], [46026, '客名', 'TEST-1', 100]])
      sheet.A2.z = 'yyyy/m/d'
      XLSX.utils.book_append_sheet(book, sheet, name)
    }
    const untouched = structuredClone(book.Sheets['华登（贸易）'])
    const result = computeHkbLedgerFills([], book, new Set([1]), { sheets: new Set(['USC（国际）']) })
    expect(Object.keys(result.stat)).toEqual(['USC（国际）'])
    expect(result.fills).toHaveLength(1)
    expect(result.fills[0].I).toBe(46026)
    fillHkbLedgerWorkbook(book, result.fills)
    expect(book.Sheets['华登（贸易）']).toEqual(untouched)
    expect(book.Sheets['USC（国际）'].J2.v).toBe('TEST-1')
    expect(computeHkbLedgerFills([], book, null, { sheets: new Set() }).fills).toEqual([])
  })
})
