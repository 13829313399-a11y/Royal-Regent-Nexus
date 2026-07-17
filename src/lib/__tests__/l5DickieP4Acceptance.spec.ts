import { readFileSync, writeFileSync } from 'node:fs'
import { strFromU8, unzipSync } from 'fflate'
import { describe, expect, it } from 'vitest'
import { createDickyCustomerQuoteWorkbook } from '@/lib/customerPriceConverters/dicky'
import { prepareP4CustomerConversion } from '@/lib/customerPriceConverters/p4CustomerAdapter'

function asArrayBuffer(bytes: Uint8Array) {
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
}

function decodeXml(value: string) {
  return value
    .replace(/&#x([0-9a-f]+);/gi, (_full, code: string) => String.fromCodePoint(Number.parseInt(code, 16)))
    .replace(/&#(\d+);/g, (_full, code: string) => String.fromCodePoint(Number(code)))
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, '\'')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
}

function readXmlAttribute(attrs: string, name: string) {
  return attrs.match(new RegExp(`\\b${name}="([^"]*)"`))?.[1] ?? ''
}

function readQuotationXml(workbook: Uint8Array) {
  const zip = unzipSync(workbook)
  const workbookXml = strFromU8(zip['xl/workbook.xml'])
  const relationshipsXml = strFromU8(zip['xl/_rels/workbook.xml.rels'])
  const quotationSheet = Array.from(workbookXml.matchAll(/<sheet\b([^>]*)\/>/g))
    .find((match) => ['quotation', 'quatation'].includes(decodeXml(readXmlAttribute(match[1], 'name')).toLowerCase()))
  if (!quotationSheet) throw new Error('L5.3 output is missing Quotation')
  const relationshipId = readXmlAttribute(quotationSheet[1], 'r:id')
  const relationship = Array.from(relationshipsXml.matchAll(/<Relationship\b([^>]*)\/>/g))
    .find((match) => readXmlAttribute(match[1], 'Id') === relationshipId)
  if (!relationship) throw new Error('L5.3 output is missing Quotation relationship')
  const target = readXmlAttribute(relationship[1], 'Target').replace(/^\/+/, '')
  const path = target.startsWith('xl/') ? target : `xl/${target}`
  return strFromU8(zip[path])
}

function cellBody(xml: string, ref: string) {
  const escapedRef = ref.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return xml.match(new RegExp(`<c\\b[^>]*\\br="${escapedRef}"[^>]*>([\\s\\S]*?)<\\/c>`))?.[1] ?? ''
}

function cellText(xml: string, ref: string) {
  const body = cellBody(xml, ref)
  const inline = Array.from(body.matchAll(/<t[^>]*>([\s\S]*?)<\/t>/g)).map((match) => match[1]).join('')
  return decodeXml(inline || body.match(/<v>([\s\S]*?)<\/v>/)?.[1] || '')
}

const enabled = process.env.L5_3_PHASE === 'p4'

describe.skipIf(!enabled)('L5.3 real Dickie P4 acceptance', () => {
  it('matches the Disney Cable baseline and exports the full customer workbook', () => {
    const baselinePath = process.env.L5_3_BASELINE_PATH
    const p4Path = process.env.L5_3_P4_PATH
    const templatePath = process.env.L5_3_TEMPLATE_PATH
    const outputPath = process.env.L5_3_CUSTOMER_OUTPUT_PATH
    if (!baselinePath || !p4Path || !templatePath || !outputPath) throw new Error('L5.3 acceptance paths are missing')

    const baseline = JSON.parse(readFileSync(baselinePath, 'utf8'))
    const source = new Uint8Array(readFileSync(p4Path))
    const prepared = prepareP4CustomerConversion(asArrayBuffer(source), 'IQ-L5-3-DICKIE-P4-v2.xlsx', 'dicky')
    const actual = prepared.result.p4QuoteData
    if (!actual) throw new Error('L5.3 Dickie P4 customer fields were not prepared')

    expect(prepared.artifact.customer).toBe('Dickie')
    expect(prepared.artifact.quoteNo).toBe('IQ-L5-3-DICKIE')
    expect(actual.clientName).toBe(baseline.client_name)
    expect(actual.quoteDate).toBe('2026-05-15')
    expect(actual.attention).toBe(baseline.attention)
    expect(actual.fromName).toContain('Dickie')
    expect(actual.projectNameEn).toBe('Disney Cable Car Series')
    expect(actual.productRows).toEqual(baseline.product_rows.map((row: Record<string, unknown>) => ({
      lineNo: row.line_no,
      itemTextEn: row.item_text_en,
      unitsPerCarton: row.units_per_carton,
      cartonCbm: row.carton_cbm,
      colorBoxSizeCm: row.color_box_size_cm,
      cartonSizeCm: row.carton_size_cm,
      productionMoq: row.production_moq,
      price40hHkd: row.price_40h_hkd,
      price20hHkd: row.price_20h_hkd,
      priceLclHkd: row.price_lcl_hkd,
    })))
    expect(actual.remarkLines).toEqual(baseline.remark_lines.map((row: Record<string, unknown>) => ({ lineNo: row.line_no, textEn: row.text_en })))
    expect(actual.materialPricesHkd).toEqual(baseline.material_prices_hkd.map((row: Record<string, unknown>) => ({ material: row.material, priceHkdLb: row.price_hkd_lb })))
    expect(actual.moldRows).toEqual(baseline.mold_rows.map((row: Record<string, unknown>) => ({
      projectNameEn: row.project_name_en,
      moldNo: row.mold_no,
      partsEn: row.parts_en,
      resin: row.resin,
      moldSize: row.mold_size,
      moldMaterial: row.mold_material,
      cavities: row.cavities,
      partsPerShot: row.parts_per_shot,
      moldCostHkd: row.mold_cost_hkd,
      remarkEn: row.remark_en,
    })))

    const workbook = createDickyCustomerQuoteWorkbook(prepared.result, readFileSync(templatePath))
    writeFileSync(outputPath, workbook)
    const quotationXml = readQuotationXml(workbook)
    expect(quotationXml).not.toContain('#NAME?')
    expect(quotationXml).not.toContain('#REF!')
    expect(cellText(quotationXml, 'C7')).toBe(baseline.client_name)
    expect(Number(cellText(quotationXml, 'K7'))).toBe(baseline.quote_date_serial)
    actual.productRows.forEach((row, index) => {
      const rowNumber = 12 + index
      expect(cellText(quotationXml, `B${rowNumber}`)).toBe(row.itemTextEn)
      expect(Number(cellText(quotationXml, `H${rowNumber}`))).toBe(row.price40hHkd)
      expect(Number(cellText(quotationXml, `I${rowNumber}`))).toBe(row.price20hHkd)
      expect(Number(cellText(quotationXml, `J${rowNumber}`))).toBe(row.priceLclHkd)
    })
    expect(cellText(quotationXml, 'B31')).toBe(actual.remarkLines.find((row) => row.lineNo === 0)?.textEn)
    expect(cellText(quotationXml, 'C46')).toBe(actual.projectNameEn)
    actual.moldRows.forEach((row, index) => {
      const rowNumber = 48 + index
      expect(cellText(quotationXml, `B${rowNumber}`)).toBe(row.moldNo)
      expect(cellText(quotationXml, `C${rowNumber}`)).toBe(row.partsEn)
      expect(Number(cellText(quotationXml, `J${rowNumber}`))).toBe(row.moldCostHkd)
    })
    expect(Number(cellText(quotationXml, 'J86'))).toBe(1_972_000)
    expect(cellBody(quotationXml, 'J86')).toContain('<f>SUM(J48:J85)</f>')
    expect(cellText(quotationXml, 'J87')).toBe(baseline.first_shot_time)
    expect(cellText(quotationXml, 'J88')).toBe(baseline.finish_time)
    expect(workbook.byteLength).toBeGreaterThan(10_000_000)
  }, 30_000)
})
