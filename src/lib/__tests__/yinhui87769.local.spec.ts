import { readFileSync, writeFileSync } from 'node:fs'
import { basename } from 'node:path'
import { expect, it } from 'vitest'
import { createYinhuiDraft, loadYinhuiDraft, saveYinhuiDraft } from '../customerPriceConverters/yinhuiDraft'
import { yinhuiExportIssues } from '../customerPriceConverters/yinhui'
import { createYinhuiCustomerQuoteWorkbook } from '../customerPriceConverters/yinhuiTemplate'
import { parseXlsxWorkbook } from '../customerPriceConverters/xlsxLite'

const file = process.env.YINHUI_87769_SAMPLE
const buffer = (bytes: Uint8Array) => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer

it.skipIf(!file)('exports all 87769 IC unit prices and reconciles both assemblies and the battery', () => {
  const original = readFileSync(file!)
  const draft = createYinhuiDraft(buffer(original), basename(file!))
  // Reviewed header from the accompanying customer quote.
  draft.result.quoteData.productName = 'GLOW VEHICLE'
  draft.result.quoteData.quoteDate = '2026-11-23'
  const result = loadYinhuiDraft(saveYinhuiDraft(draft)).result
  const data = result.quoteData
  const source = parseXlsxWorkbook(buffer(original), { valuesOnly: true, sheetNames: ['明细', '电子TX报价', '电子RX报价'] })
  const main = source.sheets.find(s => s.name === '明细')!
  expect(yinhuiExportIssues(data)).toEqual([])
  expect(data.electronic).toEqual(draft.result.quoteData.electronic)
  expect(data.electronic).toHaveLength(12)
  const output = createYinhuiCustomerQuoteWorkbook(result, buffer(readFileSync('public/templates/yinhui-customer-quote-template.bin')))
  const book = parseXlsxWorkbook(buffer(output), { includeFormulas: true })
  const bom = book.sheets[2]!
  const heading = bom.rows.findIndex(row => row[1] === "ELECTRICAL MAT'L")
  expect(heading).toBeGreaterThan(0)
  let idx = heading + 1
  for (const [name, mainRow, chipRows] of [['电子TX报价', 64, [15, 16, 17]], ['电子RX报价', 65, [23, 24, 25, 26, 27, 28]]] as const) {
    const tab = source.sheets.find(s => s.name === name)!
    const parent = bom.rows[idx++]!
    expect(parent[1]).toBe(main.rows[mainRow - 1]![2])
    let subtotal = Number(parent[9])
    for (const n of chipRows) {
      const chip = tab.rows[n - 1]!
      const line = bom.rows[idx++]!
      const unit = Number(chip[3]) / Number(main.rows[1]![13]) * 1.08 / .96
      expect(line[1]).toBe(chip[1])
      expect(line[7]).toBe(chip[2])
      expect(line[8]).toBeCloseTo(unit, 9)
      expect(line[9]).toBeCloseTo(unit * Number(chip[2]), 9)
      subtotal += Number(line[9])
    }
    expect(subtotal).toBeCloseTo(Number(main.rows[mainRow - 1]![9]), 7)
  }
  expect(bom.rows[idx]![1]).toBe(main.rows[65]![2])
  expect(bom.rows[idx]![9]).toBeCloseTo(Number(main.rows[65]![9]), 9)
  expect(bom.rows[heading]![10]).toBeCloseTo(Number(main.rows[68]![3]), 7)
  expect(book.sheets[0]!.rows[14]![7]).toBeCloseTo(Number(main.rows[68]![3]), 7)
  expect(book.sheets[0]!.rows[31]![9]).toBeCloseTo(Number(main.rows[69]![3]), 7)
  if (process.env.YINHUI_87769_OUTPUT) writeFileSync(process.env.YINHUI_87769_OUTPUT, output)
}, 60000)
