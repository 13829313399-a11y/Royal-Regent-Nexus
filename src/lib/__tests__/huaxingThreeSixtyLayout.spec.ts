import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { strFromU8, unzipSync } from 'fflate'
import { calculateHuaxing360, convertHuaxing360InternalQuote, type H360Category } from '../customerPriceConverters/huaxingThreeSixty'
import { createHuaxing360Workbook } from '../customerPriceConverters/huaxingThreeSixtyWorkbook'
import { parseXlsxWorkbook } from '../customerPriceConverters/xlsxLite'
import { huaxing360TestPricing as pricing, huaxing360TestSource as fixture, huaxing360TestReady as ready } from './fixtures/huaxing360Source'

const xml = (bytes: Uint8Array) => new DOMParser().parseFromString(strFromU8(bytes), 'application/xml')
const elements = (node: Document | Element, name: string) => Array.from(node.getElementsByTagNameNS('*', name))
const attrs = (node: Element) => Object.fromEntries(Array.from(node.attributes).filter(a => !a.name.startsWith('xmlns') && a.name !== 'spans').map(a => [a.name, a.value]))
const shape = (node: Element): unknown => ({ name: node.localName, attrs: attrs(node), children: Array.from(node.children).map(shape), text: node.children.length ? '' : node.textContent })
const parsed = (bytes: Uint8Array) => parseXlsxWorkbook(bytes.buffer as ArrayBuffer, { includeFormulas: true }).sheets[0]!

describe('Huaxing 360 native template formulas and row expansion', () => {
  it('keeps the comparison column on the same maintained scrap basis', () => {
    const settings = pricing(); settings.rates.scrap_include_labor = 0
    const result = ready(convertHuaxing360InternalQuote(fixture(), 'internal.xlsx', settings))
    const sheet = parsed(createHuaxing360Workbook(result))
    expect(sheet.rows[34]?.[14]).toBeCloseTo(calculateHuaxing360(result).scrapUsd, 12)
    expect(sheet.rows[34]?.[13]).toBe(0)
    expect(sheet.rows[49]?.[29]).toBe(0)
    expect(sheet.cellFormulas?.O35).toBe('O32*P35')
    expect(sheet.rows[47]?.[14]).toBe('匯率1美元=港幣')
  })

  it('keeps all costs visible and totals linked when electronic blocks, comments and other sections overflow', () => {
    const result = ready(convertHuaxing360InternalQuote(fixture(), 'internal.xlsx', pricing()))
    result.pricing.texts.comments = Array.from({ length: 11 }, (_, i) => `本次说明 ${i + 1}`).join('\n')
    result.costs = (['electronic', 'fabric', 'packaging', 'others', 'labor'] as H360Category[]).flatMap(category => Array.from({ length: 17 }, (_, i) => ({
      source: `${category}-${i}`, description: `${category} 本次费用 ${i}`, originalCategory: '', category, quantity: i + 1,
      sourceHkd: (i + 1) * 7.8, amountHkd: (i + 1) * 7.8, needsCategory: false,
    })))
    const bytes = createHuaxing360Workbook(result), sheet = parsed(bytes)
    expect(sheet.rows[18]?.[14]).toBeCloseTo(calculateHuaxing360(result).finalUsd, 10)
    expect(sheet.rows.flat().filter(v => typeof v === 'string' && /^本次说明/.test(v))).toHaveLength(11)
    const merges = elements(xml(unzipSync(bytes)['xl/worksheets/sheet1.xml']!), 'mergeCell').map(c => c.getAttribute('ref')!)
    for (const cost of result.costs) {
      const indices = sheet.rows.flatMap((row, i) => row[1] === cost.description ? [i + 1] : [])
      expect(indices).toHaveLength(1)
      const row = indices[0]!
      expect(sheet.rows[row - 1]?.[15]).toBeCloseTo(cost.amountHkd! / 7.8, 10)
      // A value in a lower cell of a vertical merge would be hidden in Excel.
      expect(merges.some(m => {
        const match = m.match(/^(O|P)(\d+):(O|P)(\d+)$/)
        return match && row > Number(match[2]) && row <= Number(match[4])
      })).toBe(false)
    }
  })

  it('reserves color-box and carton dimension rows before general packaging items', () => {
    const result = ready(convertHuaxing360InternalQuote(fixture(), 'internal.xlsx', pricing()))
    result.costs = ['纸箱利宝', '标签', '说明书', '防割板', '胶纸', '彩盒'].map((description, i) => ({
      source: `D${i}`, description, originalCategory: '包装', category: 'packaging', quantity: 1, sourceHkd: 7.8, amountHkd: 7.8, needsCategory: false,
    }))
    const sheet = parsed(createHuaxing360Workbook(result))
    expect(sheet.rows[171]?.[1]).toBe('彩盒')
    expect(sheet.rows[172]?.slice(2, 5)).toEqual(result.colorBox)
    expect(sheet.rows[178]?.[1] ?? '').toBe('')
    expect(sheet.rows.flat().filter(v => v === '纸箱利宝')).toHaveLength(1)
  })
})

const originalFile = process.env.HUAXING_360_TEMPLATE
describe.skipIf(!originalFile)('provided historical customer template fidelity (local only)', () => {
  it('preserves exact styles/theme, columns, row heights, cell formats, merges, page setup, logo and picture anchors', () => {
    const result = ready(convertHuaxing360InternalQuote(fixture(), 'internal.xlsx', pricing()))
    const original = unzipSync(Uint8Array.from(readFileSync(originalFile!)))
    const originalDrawing = xml(original['xl/drawings/drawing1.xml']!)
    const originalExtent = elements(elements(originalDrawing, 'xfrm')[1]!, 'ext')[0]!
    result.image = { bytes: original['xl/media/image2.png']!, extension: 'png', width: Number(originalExtent.getAttribute('cx')), height: Number(originalExtent.getAttribute('cy')) }
    const output = unzipSync(createHuaxing360Workbook(result))
    expect(output['xl/styles.xml']).toEqual(original['xl/styles.xml'])
    expect(output['xl/theme/theme1.xml']).toEqual(original['xl/theme/theme1.xml'])
    expect(output['xl/media/logo.png']).toEqual(original['xl/media/image1.png'])
    const sourceSheet = xml(original['xl/worksheets/sheet1.xml']!), targetSheet = xml(output['xl/worksheets/sheet1.xml']!)
    for (const name of ['cols', 'sheetFormatPr', 'mergeCells', 'pageMargins', 'pageSetup', 'headerFooter']) {
      expect(shape(elements(targetSheet, name)[0]!)).toEqual(shape(elements(sourceSheet, name)[0]!))
    }
    expect(elements(targetSheet, 'row').map(attrs)).toEqual(elements(sourceSheet, 'row').map(attrs))
    const sourceStyles = elements(sourceSheet, 'c').filter(c => !/^(AE|AF|AG|AH)/.test(c.getAttribute('r')!)).map(c => [c.getAttribute('r'), c.getAttribute('s') ?? '0'])
    const targetStyles = new Map(elements(targetSheet, 'c').map(c => [c.getAttribute('r'), c.getAttribute('s')]))
    for (const [ref, style] of sourceStyles) expect(targetStyles.get(ref!)).toBe(style)
    expect(shape(xml(output['xl/drawings/drawing1.xml']!).documentElement)).toEqual(shape(xml(original['xl/drawings/drawing1.xml']!).documentElement))
    // A different source aspect must fit the native frame without changing the logo or top-left.
    result.image.width = 1; result.image.height = 2
    const fitted = xml(unzipSync(createHuaxing360Workbook(result))['xl/drawings/drawing1.xml']!)
    expect(shape(fitted.documentElement.children[0]!)).toEqual(shape(originalDrawing.documentElement.children[0]!))
    const anchor = elements(fitted, 'oneCellAnchor')[0]!
    expect(shape(elements(anchor, 'from')[0]!)).toEqual(shape(elements(originalDrawing.documentElement.children[1]!, 'from')[0]!))
    const fittedExtent = elements(anchor, 'ext')[0]!
    expect(Number(fittedExtent.getAttribute('cx')) / Number(fittedExtent.getAttribute('cy'))).toBeCloseTo(.5, 5)
  })
})
