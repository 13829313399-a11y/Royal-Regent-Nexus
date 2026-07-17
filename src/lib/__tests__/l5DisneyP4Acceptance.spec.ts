import { readFileSync, writeFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import {
  convertDisneyInternalQuote,
  createDisneyCustomerQuoteWorkbook,
} from '@/lib/customerPriceConverters/disney'
import { prepareP4CustomerConversion } from '@/lib/customerPriceConverters/p4CustomerAdapter'

function asArrayBuffer(bytes: Uint8Array) {
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
}

const phase = process.env.L5_2_PHASE

describe.skipIf(!phase)('L5.2 real Disney P4 acceptance', () => {
  it('extracts the accepted source baseline or verifies and exports the P4 direct conversion', () => {
    const sourcePath = process.env.L5_2_SOURCE_PATH
    const baselinePath = process.env.L5_2_BASELINE_PATH
    if (!sourcePath || !baselinePath || !phase) throw new Error('L5.2 acceptance paths are missing')

    if (phase === 'extract') {
      const source = new Uint8Array(readFileSync(sourcePath))
      const result = convertDisneyInternalQuote(asArrayBuffer(source), sourcePath.split(/[\\/]/).pop() ?? 'Disney.xlsx')
      writeFileSync(baselinePath, JSON.stringify(result, null, 2), 'utf8')
      expect(result.sheets[0].quoteData.metadata.itemNumber).toBe('1000142435')
      expect(result.sheets[0].quoteData.plastics.length).toBeGreaterThan(5)
      expect(result.sheets[0].quoteData.moq3000Usd).toBeGreaterThan(0)
      return
    }

    const p4Path = process.env.L5_2_P4_PATH
    const templatePath = process.env.L5_2_TEMPLATE_PATH
    const outputPath = process.env.L5_2_CUSTOMER_OUTPUT_PATH
    if (!p4Path || !templatePath || !outputPath) throw new Error('L5.2 P4/output paths are missing')
    const baseline = JSON.parse(readFileSync(baselinePath, 'utf8'))
    const source = new Uint8Array(readFileSync(p4Path))
    const prepared = prepareP4CustomerConversion(asArrayBuffer(source), 'IQ-L5-2-DISNEY-P4-v2.xlsx', 'disney')
    const actual = prepared.result.sheets[0].quoteData
    const expected = baseline.sheets[0].quoteData

    expect(prepared.artifact.customer).toBe('迪士尼')
    expect(prepared.artifact.quoteNo).toBe('IQ-L5-2-DISNEY')
    expect(actual.metadata).toMatchObject({
      itemNumber: expected.metadata.itemNumber,
      itemName: expected.metadata.itemName,
      revision: expected.metadata.revision,
      moq: expected.metadata.moq,
    })
    expect(actual.plastics).toHaveLength(expected.plastics.length)
    expect(actual.plastics.map((row) => ({
      toolNo: row.toolNo,
      toolCostUsd: row.toolCostUsd,
      material: row.material,
      resinCostUsdKg: row.resinCostUsdKg,
      shotWeightG: row.shotWeightG,
      cavities: row.cavities,
      up: row.up,
      cycleTimeSeconds: row.cycleTimeSeconds,
      laborRateUsdHr: row.laborRateUsdHr,
    }))).toEqual(expected.plastics.map((row: Record<string, unknown>) => ({
      toolNo: row.toolNo,
      toolCostUsd: row.toolCostUsd,
      material: row.material,
      resinCostUsdKg: row.resinCostUsdKg,
      shotWeightG: row.shotWeightG,
      cavities: row.cavities,
      up: row.up,
      cycleTimeSeconds: row.cycleTimeSeconds,
      laborRateUsdHr: row.laborRateUsdHr,
    })))
    expect(actual.purchasedProductParts.map((row) => ({ description: row.description, perPartCostUsd: row.perPartCostUsd, included: row.included })))
      .toEqual(expected.purchasedProductParts.map((row: Record<string, unknown>) => ({ description: row.description, perPartCostUsd: row.perPartCostUsd, included: row.included })))
    expect(actual.purchasedPackageParts.map((row) => ({ description: row.description, perPartCostUsd: row.perPartCostUsd, included: row.included })))
      .toEqual(expected.purchasedPackageParts.map((row: Record<string, unknown>) => ({ description: row.description, perPartCostUsd: row.perPartCostUsd, included: row.included })))
    expect(actual.decoRows).toEqual(expected.decoRows)
    expect(actual.moq3000Usd).toBe(expected.moq3000Usd)
    expect(actual.moq5000Usd).toBe(expected.moq5000Usd)
    expect(actual.moq10000Usd).toBe(expected.moq10000Usd)
    expect(actual.modelCostUsd).toBe(expected.modelCostUsd)
    expect(actual.setupChargeUsd).toBe(expected.setupChargeUsd)

    const workbook = createDisneyCustomerQuoteWorkbook(prepared.result, readFileSync(templatePath))
    writeFileSync(outputPath, workbook)
    expect(workbook.byteLength).toBeGreaterThan(10000)
  })
})
