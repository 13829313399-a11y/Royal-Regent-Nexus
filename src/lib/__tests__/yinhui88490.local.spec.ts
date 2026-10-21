import { readFileSync } from 'node:fs'
import { basename } from 'node:path'
import { expect, it } from 'vitest'
import { createYinhuiDraft, saveYinhuiDraft, loadYinhuiDraft } from '../customerPriceConverters/yinhuiDraft'
import { yinhuiTotals } from '../customerPriceConverters/yinhui'
import { createYinhuiCustomerQuoteWorkbook } from '../customerPriceConverters/yinhuiTemplate'
import { parseXlsxWorkbook } from '../customerPriceConverters/xlsxLite'

const path = process.env.YINHUI_88490_SAMPLE
const checkedPath = process.env.YINHUI_88490_CHECKED_QUOTE
const buffer = (bytes: Uint8Array) => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer

it.skipIf(!path)('imports all 88490 parts with five packaging consumables separated and all freight routes intact', () => {
  const original = readFileSync(path!)
  const draft = createYinhuiDraft(buffer(original), basename(path!))
  const data = draft.result.quoteData
  expect(data.importIssues || []).toEqual([])
  expect(data.model).toBe('88490')
  expect(data.mechanical).toHaveLength(28)
  const packagingSources = [74, 75, 76, 77, 78].map(row => `明细!D${row}`)
  expect(data.packagingRows.filter(line => packagingSources.includes(line.source))).toHaveLength(5)
  expect(data.mechanical.some(line => packagingSources.includes(line.source))).toBe(false)
  expect(data.freightFclHkd).toBeCloseTo(.327916858600206, 10)
  expect(data.freightLclHkd).toBeCloseTo(1.23832376192443, 10)
  expect(data.freight20FtHkd).toBeCloseTo(1.05289101174954, 10)
  expect(data.freight40HqHkd).toBeCloseTo(.227149482007512, 10)
  expect(data.freightLocalHkd).toBeCloseTo(1.23832376192443, 10)
  expect(data.domesticPriceRmb).toBeCloseTo(56.2087253408366, 10)
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
  expect(bom.rows.slice(18, 46).map(row => row[1])).toEqual(data.mechanical.map(line => line.description))
  expect(bom.cellFormulas?.K18).toBe('SUM(J19:J46)')
  expect(bom.cellFormulas?.J46).toBe('I46*H46')
  expect(bom.rows[17]![10]).toBeCloseTo(yinhuiTotals(data).mechanical, 8)
  expect(output.sheets[0]!.cellFormulas?.H15).toBe("'BOM (1)'!K47")
  expect(output.sheets[0]!.rows[31]![9]).toBeCloseTo(yinhuiTotals(data).exFactory, 8)
  for (const group of ['plastic', 'electronic', 'fabric', 'packagingRows'] as const) {
    const cells = output.sheets.flatMap(sheet => sheet.rows.flat())
    for (const line of data[group] || []) expect(cells).toContain(line.description)
  }
  for (const line of data.packagingRows.filter(line => packagingSources.includes(line.source))) {
    expect(output.sheets[1]!.rows.flat()).toContain(line.description)
    expect(bom.rows.flat()).not.toContain(line.description)
  }
  const summary = output.sheets[0]!
  expect(summary.rows[32]![10]).toBe('')
  const source = parseXlsxWorkbook(buffer(original)).sheets.find(sheet => sheet.name === '明细')!
  expect(summary.rows[31]![9]).toBeCloseTo(Number(source.rows[94]![3]), 6)
  if (checkedPath) {
    const checkedBytes = readFileSync(checkedPath)
    const checked = parseXlsxWorkbook(buffer(checkedBytes)).sheets[0]!
    // The checked customer file is an independent control, never an import source.
    for (const row of [33, 34, 35, 36, 37]) {
      expect(summary.rows[row - 1]![7]).toBeCloseTo(Number(checked.rows[row - 1]![7]), 8)
      if (row === 33) expect(summary.rows[row - 1]![9]).toBeCloseTo(Number(checked.rows[row - 1]![9]), 8)
      else {
        // The checked file also has unrelated hand edits to BOM costs. Compare
        // each freight increment, preserving the original source's ex-factory price.
        expect(Number(summary.rows[row - 1]![9]) - Number(summary.rows[31]![9]))
          .toBeCloseTo(Number(checked.rows[row - 1]![9]) - Number(checked.rows[31]![9]), 8)
      }
    }
    expect(readFileSync(checkedPath)).toEqual(checkedBytes)
  }
  expect(readFileSync(path!)).toEqual(original)
}, 30000)
