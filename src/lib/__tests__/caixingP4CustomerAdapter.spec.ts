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
  const section = (
    code: P4SectionCode,
    payload: Record<string, unknown>,
    calculation: Record<string, unknown> = {},
  ) => ({
    code, name: code, status: 'approved', revision: 2, calculationStatus: 'valid', dependencyStatus: 'current', calculationHash: `${code}-hash`, isRequired: true, payload,
    calculation: { ...calculation, calculation_hash: `${code}-hash`, formula_version: 'rr2-2026-v1', reference_snapshot_id: 'IQREF-L5-4' },
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
        paper_price_factor: 2.75,
        testing_fee_total_usd: 1500,
        testing_fee_moqs: [3000, 5000, 10000],
        packaging_materials: [
          { item: '彩盒', specification: '四彩印刷', category: 'color_box_inner_card', quantity: 1, unit_price_hkd: 1.2, unit_price_source_currency: 'HKD', tax_rate_percent: 13 },
        ],
        cartons: [{
          item: '主纸箱',
          length_in: productType === 'plastic' ? 13 : 10.5,
          width_in: productType === 'plastic' ? 11 : 8.375,
          height_in: productType === 'plastic' ? 9.5 : 9.25,
          qty_per_carton: 4,
          flat_cards: [],
        }],
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
          },
        },
      }, {
        line_breakdown: [
          { kind: 'packaging_material', item: '彩盒', specification: '四彩印刷', category: 'color_box_inner_card', tax_rate_percent: 13, amount_hkd: 1.2 },
          { kind: 'carton', item: '主纸箱', carton_price_hkd: productType === 'plastic' ? 3.913 : 2.426, cuft: productType === 'plastic' ? .786 : .471, qty_per_carton: 4 },
        ],
        totals: { packaging_material_hkd: 1.2, carton_hkd: productType === 'plastic' ? .97825 : .6065 },
      }),
      engineering: section('engineering', {
        materials: [{ item: '标准五金', category: 'hardware', auxiliary_category: '五金', specification: '', quantity: 1, unit_price_hkd: .4, tax_rate_percent: 13 }], cartons: [], amortization_qty: 3000, customer_mold_subsidy_usd: 0,
        molds: [{ item: '客户模具', quantity: 1, cost_rmb: toolCost, caixing_tool_plan_ref: '1', caixing_mold_cost_hkd: toolCost * .94, caixing_customer_mold_cost_hkd: toolCost }],
      }, {
        line_breakdown: [{ kind: 'material', item: '标准五金', category: 'hardware', auxiliary_category: '五金', specification: '', tax_rate_percent: 13, amount_hkd: .4 }],
        totals: { hardware_hkd: .4, total_hkd: .4 },
      }),
      molding: section('molding', {
        injection_lines: [], blow_lines: [],
        caixing_tool_plan_rows: [{ ref_no: '1', process_type: processType, tool_no: 'T-01', tooling_cost_hkd: toolCost, description: productType === 'plastic' ? '剑柄上盖' : '公仔头', sku_no: itemNumber, cavities: productType === 'plastic' ? 2 : 12, up: productType === 'plastic' ? 2 : 12, net_weight_g: productType === 'plastic' ? 120 : 7, material_code: productType === 'plastic' ? 1 : 14, material: productType === 'plastic' ? 'ABS' : 'PVC', color: '', material_cost_hkd: productType === 'plastic' ? 1.98 : .125, machine_size: productType === 'plastic' ? '14' : 'RC', cycle_time_seconds: productType === 'plastic' ? 26 : 155, process_cost_hkd: productType === 'plastic' ? .229 : .36 }],
      }),
      electronic: section('electronic', {}, { line_breakdown: [], totals: { total_hkd: 0 } }),
      painting: section('painting', {}, { line_breakdown: [], totals: { total_hkd: 0 } }),
      slush: section('slush', {}),
      sewing: section('sewing', {}),
      hair: section('hair', {}),
      assembly: section('assembly', {}, { line_breakdown: [], totals: { assembly_hkd: 0, packaging_hkd: 0, total_hkd: 0 } }),
    },
  }
}

describe('Caixing P4 customer adapter', () => {
  it.each([
    ['plastic', 'public/templates/caixing-plastic-customer-quote-template.bin'],
    ['plush', 'public/templates/caixing-plush-customer-quote-template.bin'],
  ] as const)('maps %s metadata and derives the carton from the shared sales section', (productType, templatePath) => {
    const result = convertCaixingP4InternalQuote(artifact(productType), `IQ-L5-4-${productType}.xlsx`)
    expect(result.productType).toBe(productType)
    expect(result.sheets[0].quoteData.metadata.itemNo).toBe(productType === 'plastic' ? '68963' : '40636')
    expect(result.sheets[0].quoteData.metadata.carton).toMatchObject({
      length: productType === 'plastic' ? 13 : 10.5,
      width: productType === 'plastic' ? 11 : 8.375,
      height: productType === 'plastic' ? 9.5 : 9.25,
      cube: productType === 'plastic' ? .786 : .471,
      pcsPerCarton: 4,
      cartonPrice: productType === 'plastic' ? 3.913 : 2.426,
    })
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

  it('applies the Caixing process and material output classifications while preserving Packing column B', () => {
    const source = artifact('plastic')
    const toolRows = source.sections.molding.payload.caixing_tool_plan_rows as Array<Record<string, unknown>>
    toolRows.push({
      ref_no: 'B1',
      process_type: 'BL',
      tool_no: '',
      tooling_cost_hkd: 0,
      description: '剑身',
      sku_no: '68963',
      cavities: 1,
      up: 1,
      net_weight_g: 50,
      material_code: 11,
      material: 'LDPE',
      color: '',
      material_cost_hkd: .722,
      machine_size: 'BL',
      cycle_time_seconds: 45,
      process_cost_hkd: 1.4286,
    })
    source.sections.sales.payload.packaging_materials = [
      { item: '利宝', specification: '', category: 'leaflet_manual', quantity: 1, unit_price_hkd: .2353, unit_price_source_currency: 'HKD', tax_rate_percent: 13 },
      { item: '锡线', specification: '', category: 'other_purchase', quantity: 1, unit_price_hkd: .1412, unit_price_source_currency: 'HKD', tax_rate_percent: 0 },
      { item: '胶纸', specification: '', category: 'other_purchase', quantity: 1, unit_price_hkd: .1, unit_price_source_currency: 'HKD', tax_rate_percent: 0 },
      { item: '胶针', specification: '', category: 'other_purchase', quantity: 1, unit_price_hkd: .048, unit_price_source_currency: 'HKD', tax_rate_percent: 0 },
      { item: '彩盒', specification: '', category: 'color_box_inner_card', quantity: 1, unit_price_hkd: 1.2, unit_price_source_currency: 'HKD', tax_rate_percent: 13 },
    ]
    source.sections.sales.calculation.line_breakdown = [
      { kind: 'packaging_material', item: '利宝', category: 'leaflet_manual', tax_rate_percent: 13, amount_hkd: .2353 },
      { kind: 'packaging_material', item: '锡线', category: 'other_purchase', tax_rate_percent: 0, amount_hkd: .1412 },
      { kind: 'packaging_material', item: '胶纸', category: 'other_purchase', tax_rate_percent: 0, amount_hkd: .1 },
      { kind: 'packaging_material', item: '胶针', category: 'other_purchase', tax_rate_percent: 0, amount_hkd: .048 },
      { kind: 'packaging_material', item: '彩盒', category: 'color_box_inner_card', tax_rate_percent: 13, amount_hkd: 1.2 },
      { kind: 'carton', item: '主纸箱', carton_price_hkd: 3.913, cuft: .786, qty_per_carton: 4 },
    ]

    const engineeringMaterials = source.sections.engineering.payload.materials as Array<Record<string, unknown>>
    engineeringMaterials.push({ item: '3A碳性电池', category: 'auxiliary', auxiliary_category: '电池', specification: '', quantity: 1, unit_price_hkd: .84, unit_price_source_currency: 'HKD', tax_rate_percent: 0 })
    const engineeringBreakdown = source.sections.engineering.calculation.line_breakdown as Array<Record<string, unknown>>
    engineeringBreakdown.push({ kind: 'material', item: '3A碳性电池', category: 'auxiliary', auxiliary_category: '电池', specification: '', tax_rate_percent: 0, amount_hkd: .84 })

    source.sections.electronic.payload = {
      quote_mode: 'detail',
      components: [
        { item: 'IC', specification: '', quantity: 1, unit_price_hkd: .6942, tax_rate_percent: 13, children: [] },
        { item: '电子套装含喇叭', specification: '', quantity: 1, unit_price_hkd: 4.337, tax_rate_percent: 13, children: [] },
      ],
    }
    source.sections.electronic.calculation.line_breakdown = [
      { kind: 'electronic_component', item: 'IC', specification: '', tax_rate_percent: 13, amount_hkd: .6942 },
      { kind: 'electronic_component', item: '电子套装含喇叭', specification: '', tax_rate_percent: 13, amount_hkd: 4.337 },
    ]
    source.sections.electronic.calculation.totals = { total_hkd: 5.1339 }

    source.sections.painting.payload = { quote_mode: 'quick', quick_quote: { spray_labor_hkd: 1.4082, paint_hkd: .2959 } }
    source.sections.painting.calculation.line_breakdown = [
      { kind: 'painting_quick_paint', item: '油漆', amount_hkd: .2959 },
      { kind: 'painting_quick_labor', item: '喷油工', amount_hkd: 1.4082 },
    ]
    source.sections.painting.calculation.totals = { total_hkd: 1.7041 }

    source.sections.assembly.payload = { groups: [] }
    source.sections.assembly.calculation.line_breakdown = [
      { kind: 'assembly_process', group: '主产品', category: 'assembly', process: '装配人工', amount_hkd_pcs: 1.97 },
    ]
    source.sections.assembly.calculation.totals = { assembly_hkd: 1.97, packaging_hkd: 0, total_hkd: 1.97 }

    const result = convertCaixingP4InternalQuote(source, 'classification.xlsx')
    const summaryData = result.sheets[0].quoteData.summary
    expect(summaryData.process.moldingCasting).toBeCloseTo(.229, 6)
    expect(summaryData.process.spraying).toBeCloseTo(1.4286, 6)
    expect(summaryData.process.tampo).toBeCloseTo(1.7041, 6)
    expect(summaryData.material.specialMaterial).toBeCloseTo(.7084, 6)
    expect(summaryData.material.electronicMaterial).toBeCloseTo(4.4255, 6)
    expect(summaryData.material.purchasePart).toBeCloseTo(1.2648, 6)
    expect(summaryData.material.packagingMaterial).toBeCloseTo(2.7568, 6)

    const template = readFileSync('public/templates/caixing-plastic-customer-quote-template.bin')
    const output = createCaixingCustomerQuoteWorkbook(result, template)
    const workbook = parseXlsxWorkbook(asArrayBuffer(output))
    const templateWorkbook = parseXlsxWorkbook(asArrayBuffer(template))
    const summary = workbook.sheets.find((sheet) => sheet.name === 'Summary')
    const elect = workbook.sheets.find((sheet) => sheet.name === 'Elect')
    const purchase = workbook.sheets.find((sheet) => sheet.name === 'purchase')
    const packing = workbook.sheets.find((sheet) => sheet.name === 'Packing')
    const templatePacking = templateWorkbook.sheets.find((sheet) => sheet.name === 'Packing')

    expect(summary?.rows[18]?.[4]).toBeCloseTo(.229, 6)
    expect(summary?.rows[19]?.[4]).toBeCloseTo(1.4286, 6)
    expect(summary?.rows[20]?.[4]).toBeCloseTo(1.7041, 6)
    expect(elect?.rows[7]?.[1]).toBe('IC')
    expect(elect?.rows[20]?.[1]).toBe('电子套装含喇叭')
    expect(purchase?.rows[8]?.[1]).toBe('3A碳性电池')
    expect(packing?.rows.slice(6, 53).map((row) => row?.[1])).toEqual(
      templatePacking?.rows.slice(6, 53).map((row) => row?.[1]),
    )
    expect(packing?.rows[30]?.[2]).toBe('利宝')
    expect(packing?.rows[33]?.[2]).toBe('胶针')
    expect(packing?.rows[39]?.[2]).toBe('胶纸')
    expect(packing?.rows[42]?.[2]).toBe('锡线')
  }, 30_000)

  it('rejects mismatched customer mold prices before consumption', () => {
    const source = artifact()
    const molds = source.sections.engineering.payload.molds as Array<Record<string, unknown>>
    molds[0].caixing_customer_mold_cost_hkd = 1
    expect(() => convertCaixingP4InternalQuote(source, 'bad.xlsx')).toThrow('客户模价不一致')
  })
})
