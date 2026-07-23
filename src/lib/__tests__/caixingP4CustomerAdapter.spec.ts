import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import {
  convertCaixingP4InternalQuote,
  createCaixingCustomerQuoteWorkbook,
} from '@/lib/customerPriceConverters/caixing'
import type { P4InternalQuoteArtifact, P4SectionCode } from '@/lib/customerPriceConverters/p4Artifact'
import { parseXlsxWorkbook } from '@/lib/customerPriceConverters/xlsxLite'

function asArrayBuffer(bytes: Uint8Array) {
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
}

function artifact(productType: 'plastic' | 'plush' = 'plastic'): P4InternalQuoteArtifact {
  const itemNumber = productType === 'plastic' ? '68963' : '40636'
  const toolCost = productType === 'plastic' ? 53_623.53 : 14_220
  const processType = productType === 'plastic' ? 'IN' : 'RC'
  const section = (code: P4SectionCode, payload: Record<string, unknown>) => ({
    code, name: code, status: 'approved', revision: 2, calculationStatus: 'valid', dependencyStatus: 'current', calculationHash: `${code}-hash`, isRequired: true, payload,
    calculation: { calculation_hash: `${code}-hash`, formula_version: 'rr2-2026-v1', reference_snapshot_id: 'IQREF-L5-4' },
  })
  return {
    templateVersion: 'internal-quote-p4-v2',
    structuredDataSchemaVersion: 'internal-quote-structured-data-v1',
    quoteNo: `IQ-L5-4-${productType}`,
    versionLabel: 'V1',
    customer: '彩星',
    quantity: 3000,
    productName: productType === 'plastic' ? 'Transforming Power Sword' : 'Bijou Big Beats',
    factoryAndWorkshop: 'huaxing/华兴',
    formulaVersion: 'rr2-2026-v1',
    referenceSnapshotId: 'IQREF-L5-4',
    referenceSnapshot: { fx: { hkd_usd: 7.8 } },
    sections: {
      sales: section('sales', {
        testing_fee_total_usd: 1500,
        testing_fee_moqs: [3000, 5000, 10000],
        shipping: {
          markup_tiers: [
            { moq: 3000, markup_x: 1.18 },
            { moq: 5000, markup_x: 1.17 },
            { moq: 10000, markup_x: 1.15 },
          ],
          selected_markup_moq: 5000,
          misc_ratio: .02,
        },
        freight_calc: {
          enabled: true,
          hk40: 8000,
          hk20: 7100,
        },
        customer_quote_fields: {
          caixing: {
            product_type: productType,
            item_number: itemNumber,
            item_name: productType === 'plastic' ? 'Transforming Power Sword' : 'Bijou Big Beats',
            quote_date: productType === 'plastic' ? '2026-06-27' : '2026-06-02',
            carton_length_in: productType === 'plastic' ? 13 : 10.5,
            carton_width_in: productType === 'plastic' ? 11 : 8.375,
            carton_height_in: productType === 'plastic' ? 9.5 : 9.25,
            carton_cuft: productType === 'plastic' ? .786 : .471,
            carton_cbm: productType === 'plastic' ? .0223 : .0133,
            pcs_per_carton: 4,
            carton_price_hkd: productType === 'plastic' ? 3.913 : 2.426,
            cost_rows: [
              { group: 'purchase', tax_tag: '', category: '五金', description: '标准五金', base_cost_hkd: .4, customer_cost_hkd: .42 },
              { group: 'packing', tax_tag: '±13%', category: '彩盒/内咭', description: '吸塑咭', base_cost_hkd: 1.2, customer_cost_hkd: 1.23 },
              ...(productType === 'plush' ? [{ group: 'fabric', tax_tag: '', category: '车衣', description: '衣服/裙子', base_cost_hkd: 3.88, customer_cost_hkd: 3.9592 }] : []),
              { group: 'spraying', tax_tag: '±13%', category: '油漆', description: '喷油油漆', base_cost_hkd: .29, customer_cost_hkd: .296 },
              { group: 'assembly', tax_tag: '', category: '装配工', description: '装配人工', base_cost_hkd: 1.9, customer_cost_hkd: 1.97 },
            ],
          },
        },
      }),
      engineering: section('engineering', {
        materials: [], cartons: [], amortization_qty: 3000, customer_mold_subsidy_usd: 0,
        molds: [{ item: '客户模具', quantity: 1, cost_rmb: toolCost, caixing_tool_plan_ref: '1', caixing_mold_cost_hkd: toolCost * .94, caixing_customer_mold_cost_hkd: toolCost }],
      }),
      molding: section('molding', {
        injection_lines: [], blow_lines: [],
        caixing_tool_plan_rows: [{ ref_no: '1', process_type: processType, tool_no: 'T-01', tooling_cost_hkd: toolCost, description: productType === 'plastic' ? '剑柄上盖' : '公仔头', sku_no: itemNumber, cavities: productType === 'plastic' ? 2 : 12, up: productType === 'plastic' ? 2 : 12, net_weight_g: productType === 'plastic' ? 120 : 7, material_code: productType === 'plastic' ? 1 : 14, material: productType === 'plastic' ? 'ABS' : 'PVC', color: '', material_cost_hkd: productType === 'plastic' ? 1.98 : .125, machine_size: productType === 'plastic' ? '14' : 'RC', cycle_time_seconds: productType === 'plastic' ? 26 : 155, process_cost_hkd: productType === 'plastic' ? .229 : .36 }],
      }),
      electronic: section('electronic', {}),
      painting: section('painting', {}),
      slush: section('slush', {}),
      sewing: section('sewing', {}),
      assembly: section('assembly', {}),
    },
  }
}

describe('Caixing P4 customer adapter', () => {
  it.each([
    ['plastic', 'public/templates/caixing-plastic-customer-quote-template.bin'],
    ['plush', 'public/templates/caixing-plush-customer-quote-template.bin'],
  ] as const)('maps explicit %s fields into the customer template', (productType, templatePath) => {
    const result = convertCaixingP4InternalQuote(artifact(productType), `IQ-L5-4-${productType}.xlsx`)
    expect(result.productType).toBe(productType)
    expect(result.sheets[0].quoteData.metadata.itemNo).toBe(productType === 'plastic' ? '68963' : '40636')
    expect(result.sheets[0].quoteData.injectionRows[0]).toMatchObject({
      processType: productType === 'plastic' ? 'IN' : 'RC',
      cycleSeconds: productType === 'plastic' ? 26 : 155,
      customerMoldCostHkd: productType === 'plastic' ? 53_623.53 : 14_220,
    })

    const output = createCaixingCustomerQuoteWorkbook(result, readFileSync(templatePath))
    const workbook = parseXlsxWorkbook(asArrayBuffer(output))
    const summary = workbook.sheets.find((sheet) => sheet.name === 'Summary')
    const toolPlan = workbook.sheets.find((sheet) => sheet.name === 'Tool Plan')
    const toolRow = toolPlan?.rows.find((row) => row?.[5] === (productType === 'plastic' ? '剑柄上盖' : '公仔头'))
    expect(summary?.rows[2]?.[1]).toBe(productType === 'plastic' ? '68963' : '40636')
    expect(toolRow?.[1]).toBe(productType === 'plastic' ? 'IN' : 'RC')
    expect(toolRow?.[4]).toBe(productType === 'plastic' ? 53_623.53 : 14_220)
    expect(toolRow?.[15]).toBe(productType === 'plastic' ? 26 : 155)
    const customerText = workbook.sheets
      .flatMap((sheet) => sheet.rows)
      .flat()
      .map((value) => String(value ?? ''))
      .join('\n')
    expect(customerText).not.toMatch(/测试费用|吊柜费|报价（MOQ|杂项/)
  }, 30_000)

  it('rejects mismatched customer mold prices before consumption', () => {
    const source = artifact()
    const molds = source.sections.engineering.payload.molds as Array<Record<string, unknown>>
    molds[0].caixing_customer_mold_cost_hkd = 1
    expect(() => convertCaixingP4InternalQuote(source, 'bad.xlsx')).toThrow('客户模价不一致')
  })
})
