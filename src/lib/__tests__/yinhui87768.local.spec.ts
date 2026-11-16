import { readFileSync } from 'node:fs'
import { basename } from 'node:path'
import { expect, it } from 'vitest'
import { createYinhuiDraft, loadYinhuiDraft, saveYinhuiDraft } from '../customerPriceConverters/yinhuiDraft'
import { yinhuiExportIssues, yinhuiTotals, type YinhuiCostRow } from '../customerPriceConverters/yinhui'
import { readYinhuiSource, selectYinhuiMainSheet } from '../customerPriceConverters/yinhuiSource'
import { createYinhuiCustomerQuoteWorkbook } from '../customerPriceConverters/yinhuiTemplate'
import { parseXlsxWorkbook } from '../customerPriceConverters/xlsxLite'

const path = process.env.YINHUI_87768_SAMPLE
const buffer = (bytes: Uint8Array) => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer

it.skipIf(!path)('imports the original 87768 and reconciles both IC groups through customer workbook export', () => {
  const original = readFileSync(path!)
  const draft = createYinhuiDraft(buffer(original), basename(path!))
  const result = loadYinhuiDraft(saveYinhuiDraft(draft)).result
  const data = result.quoteData
  expect(yinhuiExportIssues(data)).toEqual([])
  expect(data.importIssues?.map(issue => [issue.code, issue.source])).toEqual(
    [45, 46, 47, 48, 49, 50].map(r => ['blank_amount', `明细 !D${r}`]),
  )
  expect(data.model).toBe('87768')
  expect(data.electronic).toEqual(draft.result.quoteData.electronic)
  expect(data.electronic).toHaveLength(9)

  const { sheets } = readYinhuiSource(buffer(original))
  const main = selectYinhuiMainSheet(sheets)!
  const fx = Number(main.rows[1]![13])
  function checkGroup(rows: YinhuiCostRow[], mainRow: number, parentQty: number, tab: string, chipRows: number[]) {
    const parent = rows[0]!
    const source = sheets.find(s => s.name === tab)!
    expect(parent.source).toBe(`${main.name}!D${mainRow}`)
    expect(parent.description).toBe(main.rows[mainRow - 1]![2])
    expect(parent.quantity).toBe(parentQty)
    expect(rows.slice(1).map(row => row.source)).toEqual(chipRows.map(r => `${tab}!E${r}`))
    chipRows.forEach((r, i) => {
      const chip = rows[i + 1]!
      const originalRow = source.rows[r - 1]!
      expect(chip.description).toBe(originalRow[1])
      expect(chip.quantity).toBe(Number(originalRow[2]) * parentQty)
      expect(chip.amountHkd).toBeCloseTo(Number(originalRow[4]) * parentQty / fx * 1.08 / .96, 10)
    })
    expect(rows.reduce((s, r) => s + r.internalHkd, 0)).toBeCloseTo(Number(main.rows[mainRow - 1]![3]), 7)
    expect(rows.reduce((s, r) => s + r.amountHkd, 0)).toBeCloseTo(Number(main.rows[mainRow - 1]![9]), 7)
  }
  checkGroup(data.electronic.slice(0, 7), 64, 1, '电子报价(RFID指令器)', [32, 33, 34, 72, 73, 74])
  checkGroup(data.electronic.slice(7), 65, 26, '电子报价(卡牌)', [11])
  expect(data.electronic[8]!.quantity).toBe(26)
  const originalElectronic = Number(main.rows[67]![3])
  const originalExFactory = Number(main.rows[68]![3])
  expect(yinhuiTotals(data).electronic).toBeCloseTo(originalElectronic, 7)
  expect(yinhuiTotals(data).exFactory).toBeCloseTo(originalExFactory, 7)
  const template = buffer(readFileSync('public/templates/yinhui-customer-quote-template.bin'))
  const output = parseXlsxWorkbook(buffer(createYinhuiCustomerQuoteWorkbook(result, template, { reviewNoticesConfirmed: true })))
  const bom = output.sheets[2]!.rows
  const heading = bom.findIndex(r => r[1] === "ELECTRICAL MAT'L")
  expect(heading).toBeGreaterThan(0)
  data.electronic.forEach((line, i) => {
    const row = bom[heading + 1 + i]!
    expect(row[1]).toBe(line.description)
    expect(row[7]).toBe(line.quantity)
    expect(row[8]).toBeCloseTo(line.amountHkd / line.quantity, 9)
    expect(row[9]).toBeCloseTo(line.amountHkd, 9)
  })
  expect(output.sheets[0]!.rows[14]![7]).toBeCloseTo(originalElectronic, 7)
  expect(output.sheets[0]!.rows[31]![9]).toBeCloseTo(originalExFactory, 7)
}, 60000)
