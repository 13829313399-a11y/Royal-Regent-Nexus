import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { strFromU8, strToU8, unzipSync, zipSync } from 'fflate'
import { describe, expect, it } from 'vitest'
import {
  convertThreeSixtyInternalQuote,
  createThreeSixtyCustomerQuoteWorkbook,
} from '@/lib/customerPriceConverters/threeSixty'
import { parseXlsxWorkbook } from '@/lib/customerPriceConverters/xlsxLite'

const enabled = process.env.L5_6_360_LEGACY === '1'
const sourcePath = 'C:/Users/Aalyaan/Desktop/AI入报价单(1)/AI入报价单/Toy Doll Cuddle Baby Mommy and Me BOM(2026-6-26）.xlsx'
const outputDir = 'outputs/customer-price-conversion/l5-6-360'
const outputPath = `${outputDir}/360-legacy-customer.xlsx`
const dailyOutputPath = `${outputDir}/360-daily-without-breakdown-customer.xlsx`

function readArrayBuffer(path: string) {
  const bytes = readFileSync(path)
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
}

function withoutBreakdownSheet(source: ArrayBuffer) {
  const zip = unzipSync(new Uint8Array(source))
  const workbookXml = strFromU8(zip['xl/workbook.xml'])
  zip['xl/workbook.xml'] = strToU8(
    workbookXml.replace(/<sheet\b[^>]*\bname="Breakdown"[^>]*\/>/, ''),
  )
  const bytes = zipSync(zip)
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
}

describe.skipIf(!enabled)('L5.6 360 legacy real-source acceptance', () => {
  it('converts the original multi-sheet workbook into the sanitized Breakdown output', () => {
    expect(existsSync(sourcePath)).toBe(true)
    const result = convertThreeSixtyInternalQuote(readArrayBuffer(sourcePath), sourcePath.split('/').pop()!)
    const data = result.sheets[0].quoteData

    expect(data.metadata).toMatchObject({
      productName: 'Toy Doll Cuddle Baby Mommy and Me',
      preparedBy: 'Wong Kin On',
      quoteDate: '2026-06-26',
      quantity: 20_000,
      containerType: '40HQ',
      quantityPerContainer: 1700,
    })
    expect(data.plasticRows.map((row) => row.description)).toEqual([
      '鞋子',
      '搪胶头',
      '搪胶手',
      '搪胶脚',
    ])
    expect(data.purchaseRows).toHaveLength(1)
    expect(data.fabricRows).toHaveLength(6)
    expect(data.packagingRows).toHaveLength(6)
    expect(data.otherRows).toHaveLength(1)
    expect(data.carton).toMatchObject({
      lengthIn: 24.75,
      widthIn: 19.25,
      heightIn: 17,
      qtyPerCarton: 4,
    })

    const template = readFileSync('public/templates/360-customer-quote-template.bin')
    const output = createThreeSixtyCustomerQuoteWorkbook(result, template)
    mkdirSync(outputDir, { recursive: true })
    writeFileSync(outputPath, output)

    const workbook = parseXlsxWorkbook(
      output.buffer.slice(output.byteOffset, output.byteOffset + output.byteLength) as ArrayBuffer,
    )
    expect(workbook.sheets.map((sheet) => sheet.name)).toEqual(['Breakdown'])
    expect(workbook.sheets[0].rows[11]?.[2]).toBe('Toy Doll Cuddle Baby Mommy and Me')
    expect(workbook.sheets[0].rows[59]?.[1]).toBe('鞋子')
    expect(workbook.sheets[0].rows[63]?.[1]).toBe('')

    const packageText = Object.entries(unzipSync(output))
      .filter(([path]) => path.endsWith('.xml') || path.endsWith('.rels'))
      .map(([, value]) => strFromU8(value))
      .join('\n')
    expect(packageText).not.toMatch(/#REF!|#NAME\?/)

    const dailyResult = convertThreeSixtyInternalQuote(
      withoutBreakdownSheet(readArrayBuffer(sourcePath)),
      sourcePath.split('/').pop()!,
    )
    expect(dailyResult.sheets[0].quoteData.metadata).toMatchObject({
      productName: 'Toy Doll Cuddle Baby Mommy and Me',
      preparedBy: '郑大能',
      quoteDate: '2026-06-26',
      quantity: 20_000,
      quantityPerContainer: 1700,
    })
    expect(dailyResult.sheets[0].quoteData.plasticRows.map((row) => row.description)).toEqual([
      '鞋子',
      '搪胶头',
      '搪胶手',
      '搪胶脚',
    ])
    const dailyOutput = createThreeSixtyCustomerQuoteWorkbook(dailyResult, template)
    writeFileSync(dailyOutputPath, dailyOutput)
    const dailyWorkbook = parseXlsxWorkbook(
      dailyOutput.buffer.slice(
        dailyOutput.byteOffset,
        dailyOutput.byteOffset + dailyOutput.byteLength,
      ) as ArrayBuffer,
    )
    expect(dailyWorkbook.sheets.map((sheet) => sheet.name)).toEqual(['Breakdown'])
    expect(dailyWorkbook.sheets[0].rows[9]?.[14]).toBe('郑大能')
    expect(dailyWorkbook.sheets[0].rows[11]?.[14]).toBe(46199)
  }, 120_000)
})
