import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import {
  convertCaixingInternalQuote,
  createCaixingCustomerQuoteWorkbook,
} from '@/lib/customerPriceConverters/caixing'
import { prepareP4CustomerConversion } from '@/lib/customerPriceConverters/p4CustomerAdapter'
import { parseXlsxWorkbook } from '@/lib/customerPriceConverters/xlsxLite'

const outputDir = 'outputs/customer-price-conversion/l5-4-caixing'
const phase = process.env.L5_4_PHASE ?? ''
const plasticSourcePath = 'C:/Users/Aalyaan/Desktop/彩星/塑胶/68963发声亮灯剑报价（按图报价）－2026-6-27.xlsx'
const plushSourcePath = 'C:/Users/Aalyaan/Desktop/彩星/毛绒/40636－1款5寸公仔套装报价（按图报价）－2026-6－2（内部）.xlsx'

function readArrayBuffer(path: string) {
  const bytes = readFileSync(path)
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
}

describe.skipIf(!phase)('L5.4 Caixing P4 real-source acceptance', () => {
  it('extracts the authoritative plastic and plush baselines', () => {
    if (phase !== 'extract') return
    expect(existsSync(plasticSourcePath)).toBe(true)
    expect(existsSync(plushSourcePath)).toBe(true)
    mkdirSync(outputDir, { recursive: true })

    const plastic = convertCaixingInternalQuote(
      readArrayBuffer(plasticSourcePath),
      '68963发声亮灯剑报价（按图报价）－2026-6-27.xlsx',
      'plastic',
    )
    const plush = convertCaixingInternalQuote(
      readArrayBuffer(plushSourcePath),
      '40636－1款5寸公仔套装报价（按图报价）－2026-6－2（内部）.xlsx',
      'plush',
    )

    writeFileSync(`${outputDir}/plastic-baseline.json`, JSON.stringify(plastic, null, 2))
    writeFileSync(`${outputDir}/plush-baseline.json`, JSON.stringify(plush, null, 2))
    writeFileSync(`${outputDir}/plastic-manual-customer.xlsx`, createCaixingCustomerQuoteWorkbook(plastic, readArrayBuffer('public/templates/caixing-plastic-customer-quote-template.bin')))
    writeFileSync(`${outputDir}/plush-manual-customer.xlsx`, createCaixingCustomerQuoteWorkbook(plush, readArrayBuffer('public/templates/caixing-plush-customer-quote-template.bin')))

    expect(plastic.sheets[0].quoteData.injectionRows.length).toBeGreaterThan(0)
    expect(plastic.sheets[0].quoteData.costRows.length).toBeGreaterThan(0)
    expect(plush.sheets[0].quoteData.injectionRows.length).toBeGreaterThan(0)
    expect(plush.sheets[0].quoteData.costRows.length).toBeGreaterThan(0)
  }, 120_000)

  it('converts both released P4 workbooks into the plastic and plush templates', () => {
    if (phase !== 'p4') return
    const cases = [
      {
        productType: 'plastic' as const,
        itemNo: '68963',
        p4Path: process.env.L5_4_PLASTIC_P4_PATH!,
        templatePath: 'public/templates/caixing-plastic-customer-quote-template.bin',
        outputPath: process.env.L5_4_PLASTIC_OUTPUT_PATH!,
      },
      {
        productType: 'plush' as const,
        itemNo: '40636',
        p4Path: process.env.L5_4_PLUSH_P4_PATH!,
        templatePath: 'public/templates/caixing-plush-customer-quote-template.bin',
        outputPath: process.env.L5_4_PLUSH_OUTPUT_PATH!,
      },
    ]
    for (const item of cases) {
      expect(existsSync(item.p4Path)).toBe(true)
      const prepared = prepareP4CustomerConversion(
        readArrayBuffer(item.p4Path),
        item.p4Path.split(/[\\/]/).pop() ?? 'P4.xlsx',
        'caixing',
        { quoteNo: `IQ-L5-4-CAIXING-${item.productType.toUpperCase()}`, versionLabel: 'V1', customer: '彩星', quantity: 3000 },
      )
      expect(prepared.customerId).toBe('caixing')
      expect(prepared.result.productType).toBe(item.productType)
      expect(prepared.result.sheets[0].quoteData.metadata.itemNo).toBe(item.itemNo)
      expect(prepared.result.sheets[0].quoteData.injectionRows.length).toBeGreaterThan(0)
      expect(prepared.result.sheets[0].quoteData.costRows.length).toBeGreaterThan(0)
      const output = createCaixingCustomerQuoteWorkbook(prepared.result, readArrayBuffer(item.templatePath))
      writeFileSync(item.outputPath, output)
      const workbook = parseXlsxWorkbook(output.buffer.slice(output.byteOffset, output.byteOffset + output.byteLength) as ArrayBuffer)
      const summary = workbook.sheets.find((sheet) => sheet.name === 'Summary')
      const toolPlan = workbook.sheets.find((sheet) => sheet.name === 'Tool Plan')
      expect(summary?.rows[2]?.[1]).toBe(item.itemNo)
      expect(toolPlan?.rows.some((row) => ['IN', 'BL', 'RC'].includes(String(row?.[1] ?? '')) && Number(row?.[15]) > 0)).toBe(true)
      expect(prepared.result.sheets[0].totalCustomerHkd).toBeGreaterThan(0)
    }
  }, 120_000)
})
