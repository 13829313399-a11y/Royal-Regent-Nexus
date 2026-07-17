import { readFileSync, writeFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { prepareP4CustomerConversion } from '@/lib/customerPriceConverters/p4CustomerAdapter'
import { createBuzzBeeCustomerQuoteWorkbook } from '@/lib/customerPriceConverters/buzzbee'
import { parseXlsxWorkbook } from '@/lib/customerPriceConverters/xlsxLite'

function asArrayBuffer(bytes: Uint8Array) {
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
}

describe.skipIf(!process.env.L5_PHASE)('L5.1 real BuzzBee P4 acceptance', () => {
  it('preflights the controlled P4 artifact and generates the customer workbook after receipt', () => {
    const p4Path = process.env.L5_P4_PATH
    const previewPath = process.env.L5_PREVIEW_PATH
    const customerOutputPath = process.env.L5_CUSTOMER_OUTPUT_PATH
    const phase = process.env.L5_PHASE
    if (!p4Path || !previewPath || !customerOutputPath || !phase) throw new Error('L5.1 acceptance paths are missing')

    const source = new Uint8Array(readFileSync(p4Path))
    const prepared = prepareP4CustomerConversion(asArrayBuffer(source), 'IQ-L5-1-BUZZBEE-P4-v2.xlsx', 'buzzbee')
    const sheet = prepared.result.sheets[0]

    expect(prepared.artifact.customer).toBe('BuzzBee')
    expect(prepared.artifact.quoteNo).toBe('IQ-L5-1-BUZZBEE')
    expect(sheet.productName).toBe('露营火堆套装')
    expect(sheet.quoteData.injectionRows).toHaveLength(12)
    expect(sheet.quoteData.injectionRows.map((row) => row.material)).toEqual([
      'ABS', 'ABS', 'ABS', 'PE', 'ABS', 'ABS', 'PP', 'PP', 'PP', 'ABS', 'ABS', 'C-ABS',
    ])
    expect(sheet.quoteData.box).toMatchObject({ length: 14, width: 9.25, height: 23.875, pcsPerCarton: 2 })
    expect(sheet.quoteData.colorBox).toMatchObject({ price1: 6.7, fsc1: 3.4505, moq1: 'MOQ3000', price2: 5.75, fsc2: 2.9613, moq2: 'MOQ20000' })
    expect(sheet.totalCustomerHkd).toBeGreaterThan(40)

    const preview = {
      phase: '转换预览',
      quoteNo: prepared.artifact.quoteNo,
      customer: prepared.artifact.customer,
      productName: sheet.productName,
      injectionRows: sheet.quoteData.injectionRows.length,
      detailRows: sheet.details.length,
      totalInternalHkd: sheet.totalInternalHkd,
      totalCustomerHkd: sheet.totalCustomerHkd,
      colorBox: sheet.quoteData.colorBox,
    }
    writeFileSync(previewPath, `${JSON.stringify(preview, null, 2)}\n`, 'utf8')

    if (phase === 'preflight') return
    if (phase !== 'output') throw new Error(`unknown L5.1 phase: ${phase}`)

    const output = createBuzzBeeCustomerQuoteWorkbook(prepared.result)
    writeFileSync(customerOutputPath, output)
    const exported = parseXlsxWorkbook(asArrayBuffer(output)).sheets[0]
    expect(exported.rows[0][0]).toBe('COST BREAKDOWN SHEET (ROYAL REGENT)')
    const cartonRow = exported.rows.find((row) => row?.[0] === 'CARTON SIZE')
    const outerRow = exported.rows.find((row) => row?.[0] === 'OUTTER')
    expect(cartonRow?.[1]).toBe(14)
    expect(cartonRow?.[2]).toBe(9.25)
    expect(cartonRow?.[3]).toBe(23.875)
    expect(cartonRow?.[5]).toBe(3.35)
    expect(cartonRow?.[6]).toBe(3.4505)
    expect(cartonRow?.[7]).toBe('MOQ3000')
    expect(outerRow?.[1]).toBe(2)
  })
})
