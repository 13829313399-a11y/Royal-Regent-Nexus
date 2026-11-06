import { readFileSync, writeFileSync } from 'node:fs'
import { basename } from 'node:path'
import { expect, it } from 'vitest'
import { createYinhuiDraft, correctYinhuiDraft, saveYinhuiDraft, loadYinhuiDraft } from '../customerPriceConverters/yinhuiDraft'
import { yinhuiTotals, validateYinhuiExport } from '../customerPriceConverters/yinhui'
import { createYinhuiCustomerQuoteWorkbook } from '../customerPriceConverters/yinhuiTemplate'
import { readYinhuiSource } from '../customerPriceConverters/yinhuiSource'
import { parseXlsxWorkbook } from '../customerPriceConverters/xlsxLite'

const path = process.env.YINHUI_MT28_SAMPLE
const buffer = (bytes: Uint8Array) => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer

it.skipIf(!path)('keeps MT28 missing amounts visible and exports every packaging line after informed confirmation', () => {
  const original = readFileSync(path!)
  const source = readYinhuiSource(buffer(original)).sheets.find(s => s.name === '明细')!
  for (const r of [62, 63, 64]) {
    expect(source.rows[r - 1]?.[3] ?? '').toBe('')
    expect(source.cellFormulas?.[`D${r}`]).toBeUndefined()
    expect(source.rows[r - 1]?.[4]).toBe(0)
  }
  const draft = createYinhuiDraft(buffer(original), basename(path!))
  expect(draft.result.quoteData.importIssues?.map(i => i.source)).toEqual(['明细!D62', '明细!D63', '明细!D64'])
  expect(draft.result.quoteData.importIssues?.every(i => i.message.includes('为空白'))).toBe(true)
  expect(draft.result.quoteData.packagingRows).toHaveLength(26)
  expect(draft.result.quoteData.packagingRows.filter(r => r.pricePending)).toHaveLength(3)
  expect(() => validateYinhuiExport(draft.result.quoteData)).toThrow(/确认/)
  const template = buffer(readFileSync('public/templates/yinhui-customer-quote-template.bin'))
  const pending = parseXlsxWorkbook(buffer(createYinhuiCustomerQuoteWorkbook(draft.result, template, { reviewNoticesConfirmed: true })))
  const pendingRows = pending.sheets[1]!.rows.filter(r => String(r[1]).includes('[PRICE PENDING]'))
  expect(pendingRows).toHaveLength(3)
  pendingRows.forEach(r => { expect(r[8] ?? '').toBe(''); expect(r[9] ?? '').toBe('') })
  expect(pending.sheets[0]!.rows[5]?.[2]).toContain('PRICE PENDING')

  // The user confirmed these three items are included elsewhere. Replay that
  // explicit correction without making blank-to-zero a general import rule.
  const fixed = correctYinhuiDraft(draft, [62, 63, 64].map(r => ({ sheet: '明细', cell: `D${r}`, value: 0 })))
  const data = fixed.result.quoteData
  expect(data.importIssues).toEqual([])
  expect(data.packagingRows).toHaveLength(26)
  expect(data.packagingRows.filter(r => ['明细!D62', '明细!D63', '明细!D64'].includes(r.source))).toHaveLength(3)
  expect(yinhuiTotals(data)).toEqual(yinhuiTotals(draft.result.quoteData))
  const restored = loadYinhuiDraft(saveYinhuiDraft(fixed))
  expect(restored.result.quoteData.packagingRows).toEqual(data.packagingRows)
  expect(restored.result.quoteData.importIssues).toEqual([])
  expect(yinhuiTotals(data).injection).toBeCloseTo(Number(source.rows[24]?.[4]), 8)
  expect(yinhuiTotals(data).exFactory).toBeCloseTo(Number(source.rows[98]?.[3]), 6)
  expect(fixed.result.warnings.some(w => w.includes('1.05 倍啤工汇总倍率'))).toBe(true)
  const out = parseXlsxWorkbook(buffer(createYinhuiCustomerQuoteWorkbook(restored.result, template, { reviewNoticesConfirmed: true })), { includeFormulas: true })
  expect(out.sheets[0]!.rows[3]?.[2]).toBe(data.productName)
  const rows = out.sheets[1]!.rows.slice(32, 58)
  expect(rows.map(r => r[1])).toEqual(data.packagingRows.map(r => r.description))
  rows.forEach((r, i) => {
    expect(r[7]).toBe(data.packagingRows[i]!.quantity)
    expect(r[9]).toBeCloseTo(data.packagingRows[i]!.amountHkd, 8)
  })
  expect(out.sheets[1]!.cellFormulas?.K32).toBe('SUM(J33:J61)')
  expect(out.sheets[0]!.rows[31]?.[9]).toBeCloseTo(yinhuiTotals(data).exFactory, 8)
  expect(readFileSync(path!)).toEqual(original)
  if (process.env.YINHUI_MT28_DRAFT_OUTPUT) writeFileSync(process.env.YINHUI_MT28_DRAFT_OUTPUT, saveYinhuiDraft(fixed), 'utf8')
}, 90000)
