import { readFileSync } from 'node:fs'
import { basename } from 'node:path'
import { expect, it } from 'vitest'
import { createYinhuiDraft, saveYinhuiDraft, loadYinhuiDraft } from '../customerPriceConverters/yinhuiDraft'
import { yinhuiTotals } from '../customerPriceConverters/yinhui'
import { createYinhuiCustomerQuoteWorkbook } from '../customerPriceConverters/yinhuiTemplate'
import { parseXlsxWorkbook } from '../customerPriceConverters/xlsxLite'

const path = process.env.YINHUI_88490_SAMPLE
const buffer = (bytes: Uint8Array) => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer

it.skipIf(!path)('imports all 88490 purchased parts and exports all 33 mechanical rows without changing the source', () => {
  const original = readFileSync(path!)
  const draft = createYinhuiDraft(buffer(original), basename(path!))
  const data = draft.result.quoteData
  expect(data.importIssues || []).toEqual([])
  expect(data.model).toBe('88490')
  expect(data.mechanical).toHaveLength(33)
  expect(data.plastic.find(line => line.source === '明细!D68')).toMatchObject({
    internalHkd: .26, quantity: 1,
  })
  expect(data.plastic.find(line => line.source === '明细!D68')!.amountHkd).toBeCloseTo(.311458333333333, 8)
  const restored = loadYinhuiDraft(saveYinhuiDraft(draft))
  expect(restored.result.quoteData.importIssues || []).toEqual([])
  expect(restored.result.quoteData.mechanical).toEqual(data.mechanical)
  expect(restored.result.quoteData.plastic).toEqual(data.plastic)

  // Test-only labels satisfy the existing English-name gate; no customer file is delivered.
  const result = structuredClone(draft.result)
  result.quoteData.productName = 'Test Product'
  result.quoteData.tools.forEach((line, i) => { line.description = `Test Tool ${i + 1}` })
  const template = readFileSync('public/templates/yinhui-customer-quote-template.bin')
  const output = parseXlsxWorkbook(buffer(createYinhuiCustomerQuoteWorkbook(result, buffer(template))), { includeFormulas: true })
  const bom = output.sheets[2]!
  expect(bom.rows.slice(18, 51).map(row => row[1])).toEqual(data.mechanical.map(line => line.description))
  expect(bom.cellFormulas?.K18).toBe('SUM(J19:J51)')
  expect(bom.cellFormulas?.J51).toBe('I51*H51')
  expect(bom.rows[17]![10]).toBeCloseTo(yinhuiTotals(data).mechanical, 8)
  expect(output.sheets[0]!.cellFormulas?.H15).toBe("'BOM (1)'!K52")
  expect(output.sheets[0]!.rows[31]![9]).toBeCloseTo(yinhuiTotals(data).exFactory, 8)
  for (const group of ['plastic', 'electronic', 'fabric', 'packagingRows'] as const) {
    const cells = output.sheets.flatMap(sheet => sheet.rows.flat())
    for (const line of data[group] || []) expect(cells).toContain(line.description)
  }
  expect(readFileSync(path!)).toEqual(original)
}, 30000)
