import { createHash } from 'node:crypto'
import { readFileSync, writeFileSync } from 'node:fs'
import { basename } from 'node:path'
import { expect, it } from 'vitest'
import { strFromU8, strToU8, unzipSync, zipSync } from 'fflate'
import { createYinhuiDraft, loadYinhuiDraft, saveYinhuiDraft } from '../customerPriceConverters/yinhuiDraft'
import { readYinhuiSource } from '../customerPriceConverters/yinhuiSource'
import { readYinhuiElectronicSources, splitYinhuiLegacyElectronics } from '../customerPriceConverters/yinhuiElectronic'
import { yinhuiTotals } from '../customerPriceConverters/yinhui'
import { createYinhuiCustomerQuoteWorkbook } from '../customerPriceConverters/yinhuiTemplate'
import { parseXlsxWorkbook } from '../customerPriceConverters/xlsxLite'

const path = process.env.YINHUI_88578_SAMPLE
const buffer = (bytes: Uint8Array) => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer

it.skipIf(!path)('matches every original 88578 IC to its TX/RX parent and preserves group totals through draft/export', () => {
  const original = readFileSync(path!)
  // The user may apply the temporary title workaround during verification.
  // Replay only the two previously observed title fragments in memory; never
  // write the source file or use source overrides to bypass draft validation.
  const zip = unzipSync(original)
  let replayedTitles = 0
  for (const [name, bytes] of Object.entries(zip)) {
    if (!/^xl\/(?:sharedStrings\.xml|worksheets\/[^/]+\.xml)$/.test(name)) continue
    const xml = strFromU8(bytes)
    const replay = xml.replace(/产品编号：88578-(TX|RX)(?=\s)/g, (_, role: string) => {
      replayedTitles++
      return `产品编号：88578-红外 ${role}`
    })
    if (replay !== xml) zip[name] = strToU8(replay)
  }
  const originalTitles = replayedTitles ? zipSync(zip) : original
  const workbook = readYinhuiSource(buffer(originalTitles))
  const main = workbook.sheets.find(s => s.name === '明细')!
  const electronic = workbook.sheets.find(s => s.name.trim() === '电子报价')!
  expect(electronic.rows[4]?.[0]).toContain('88578-红外 TX')
  expect(electronic.rows[57]?.[0]).toContain('88578-红外 RX')
  const sources = readYinhuiElectronicSources(workbook.sheets)
  expect(sources.map(g => [g.model, g.role, g.chips.map(c => c.source)])).toEqual([
    ['88578', 'TX', ['电子报价 !E8', '电子报价 !E28']],
    ['88578', 'RX', ['电子报价 !E75', '电子报价 !E76', '电子报价 !E77', '电子报价 !E78']],
  ])
  sources.forEach((group, i) => expect(group.chips.reduce((sum, c) => sum + c.amount, 0)).toBeCloseTo([.6, 1.81][i]!, 10))
  const actual = createYinhuiDraft(buffer(original), basename(path!))
  expect(actual.result.quoteData.importIssues).toEqual([])
  const draft = createYinhuiDraft(buffer(originalTitles), basename(path!))
  const data = draft.result.quoteData
  expect(data.model).toBe('88578')
  expect(data.importIssues).toEqual([])
  expect(data.electronic).toEqual(actual.result.quoteData.electronic)
  const rows = data.electronic.filter(r => !r.isBattery)
  const expectedSources = ['明细!D76', '电子报价 !E8', '电子报价 !E28', '明细!D77', '电子报价 !E75', '电子报价 !E76', '电子报价 !E77', '电子报价 !E78']
  expect(rows.map(r => r.source)).toEqual(expectedSources)
  const grouped = [rows.slice(0, 3), rows.slice(3)]
  const parentAmounts = [2.23 / .84, 7.24 / .84]
  grouped.forEach((group, i) => {
    expect(group[0]!.description).toContain(i === 0 ? 'TX' : 'RX')
    expect(group.reduce((sum, r) => sum + r.internalHkd, 0)).toBeCloseTo(parentAmounts[i]!, 10)
    expect(group.reduce((sum, r) => sum + r.amountHkd, 0)).toBeCloseTo(parentAmounts[i]! * 1.08 / .96, 8)
    expect(group[0]!.amountHkd).toBeGreaterThan(0)
    group.slice(1).forEach((row, index) => {
      const chip = sources[i]!.chips[index]!
      expect(row.description).toBe(chip.description)
      expect(row.quantity).toBe(chip.quantity)
      expect(row.internalHkd).toBeCloseTo(chip.amount / .84, 10)
      expect(row.amountHkd).toBeCloseTo(chip.amount / .84 * 1.08 / .96, 10)
    })
  })
  const parents = grouped.map((group, i) => ({ ...group[0]!, internalHkd: parentAmounts[i]!, amountHkd: parentAmounts[i]! * 1.08 / .96 }))
  const reversed = splitYinhuiLegacyElectronics(parents.reverse(), workbook.sheets, main, '88578')
  expect(reversed.map(r => r.source)).toEqual([...expectedSources.slice(3), ...expectedSources.slice(0, 3)])
  const restored = loadYinhuiDraft(saveYinhuiDraft(draft))
  expect(restored.result.quoteData.electronic).toEqual(data.electronic)
  const template = buffer(readFileSync('public/templates/yinhui-customer-quote-template.bin'))
  const exported = parseXlsxWorkbook(buffer(createYinhuiCustomerQuoteWorkbook(restored.result, template, { reviewNoticesConfirmed: true, missingMaterialPricesConfirmed: true })))
  const outputRows = exported.sheets.flatMap(s => s.rows).filter(r => rows.some(line => r[1] === line.description))
  rows.forEach(line => {
    const matches = outputRows.filter(r => r[1] === line.description)
    expect(matches).toHaveLength(1)
    expect(matches[0]?.[7]).toBe(line.quantity)
    expect(matches[0]?.[9]).toBeCloseTo(line.amountHkd, 8)
  })
  expect(exported.sheets[0]!.rows[31]?.[9]).toBeCloseTo(yinhuiTotals(data).exFactory, 6)
  expect(readFileSync(path!)).toEqual(original)
  if (process.env.YINHUI_88578_REPORT) writeFileSync(process.env.YINHUI_88578_REPORT, JSON.stringify({
    sourceSha256: createHash('sha256').update(original).digest('hex'), sourceUnchanged: true,
    replayedTitles,
    importIssues: data.importIssues, groups: sources, rows, totals: yinhuiTotals(data),
    groupTotals: grouped.map(group => ({ role: group[0]!.description, internalHkd: group.reduce((sum, r) => sum + r.internalHkd, 0), amountHkd: group.reduce((sum, r) => sum + r.amountHkd, 0) })),
    exportedElectronicRows: outputRows,
  }, null, 2))
}, 90000)
