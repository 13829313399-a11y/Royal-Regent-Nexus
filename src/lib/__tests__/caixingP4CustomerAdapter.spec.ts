import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { strFromU8, unzipSync } from 'fflate'
import {
  convertCaixingP4InternalQuote,
  createCaixingCustomerQuoteWorkbook,
  buildCaixingCustomerQuoteFileName,
} from '@/lib/customerPriceConverters/caixing'
import type { CustomerPricingSettings } from '@/lib/customerPriceConverters/pricingSettings'
import type { P4InternalQuoteArtifact, P4SectionCode } from '@/lib/customerPriceConverters/p4Artifact'
import { parseXlsxWorkbook } from '@/lib/customerPriceConverters/xlsxLite'

function asArrayBuffer(bytes: Uint8Array) {
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
}

function caixingPricing(): CustomerPricingSettings {
  const definitions = JSON.parse(readFileSync('shared/customerPriceDefaults.json', 'utf8')).caixing.rates as Record<string, { value: number }>
  return { factory_id: 'huaxing', customer_id: 'caixing', revision: 0, materials: [],
    rates: Object.fromEntries(Object.entries(definitions).map(([key, row]) => [key, row.value])),
    texts: {}, updated_at: '', updated_by_name: '', snapshot_id: 'caixing-test-snapshot' }
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
    const workbook = parseXlsxWorkbook(asArrayBuffer(output), { includeFormulas: true })
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
    expect(summaryData.material.specialMaterial).toBeCloseTo(.7226, 6)
    expect(summaryData.material.electronicMaterial).toBeCloseTo(4.514, 6)
    expect(summaryData.material.purchasePart).toBeCloseTo(1.2648, 6)
    expect(summaryData.material.packagingMaterial).toBeCloseTo(2.7568, 6)

    const template = readFileSync('public/templates/caixing-plastic-customer-quote-template.bin')
    const output = createCaixingCustomerQuoteWorkbook(result, template)
    const workbook = parseXlsxWorkbook(asArrayBuffer(output), { includeFormulas: true })
    const templateWorkbook = parseXlsxWorkbook(asArrayBuffer(template))
    const summary = workbook.sheets.find((sheet) => sheet.name === 'Summary')
    const elect = workbook.sheets.find((sheet) => sheet.name === 'Elect')
    const purchase = workbook.sheets.find((sheet) => sheet.name === 'purchase')
    const packing = workbook.sheets.find((sheet) => sheet.name === 'Packing')
    const templatePacking = templateWorkbook.sheets.find((sheet) => sheet.name === 'Packing')

    expect(summary?.rows[18]?.[4]).toBeCloseTo(.229, 6)
    expect(summary?.rows[19]?.[4]).toBeCloseTo(1.4286, 6)
    expect(summary?.rows[19]?.[2]).toBe(1)
    expect(summary?.rows[19]?.[3]).toBeCloseTo(1.4286, 6)
    expect(summary?.cellFormulas?.E20).toBe('C20*D20')
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

  it('uses separate plush scrap and markup rules for materials, electronics and sewing labor', () => {
    const source = artifact('plush')
    source.sections.electronic.calculation.line_breakdown = [
      { kind: 'electronic_component', item: 'IC', amount_hkd: 1 },
      { kind: 'electronic_component', item: 'Speaker', amount_hkd: 2 },
    ]
    source.sections.electronic.calculation.totals = { total_hkd: 3 }
    source.sections.sewing.calculation.line_breakdown = [
      { kind: 'sewing_material', category: 'clothes', cost_kind: 'material', item: 'Dress fabric', amount_hkd: 2 },
    ]
    source.sections.sewing.calculation.pricing_breakdown = [
      { kind: 'sewing_labor', category: 'clothes', cost_kind: 'labor', item: 'Sewing labor', amount_hkd: 1 },
    ]
    source.sections.sewing.calculation.totals = { clothes_hkd: 3, hair_hkd: 0 }
    const pricing = caixingPricing()
    const result = convertCaixingP4InternalQuote(source, 'plush.xlsx', pricing)
    const summaryData = result.sheets[0].quoteData.summary
    expect(summaryData.material.specialMaterial).toBeCloseTo(1.02, 6)
    expect(summaryData.material.electronicMaterial).toBeCloseTo(2.04, 6)
    expect(summaryData.material.fabric).toBeCloseTo(3.04, 6)
    const output = createCaixingCustomerQuoteWorkbook(result, readFileSync('public/templates/caixing-plush-customer-quote-template.bin'))
    const workbook = parseXlsxWorkbook(asArrayBuffer(output))
    const summary = workbook.sheets.find((sheet) => sheet.name === 'Summary')!
    const fabric = workbook.sheets.find((sheet) => sheet.name === 'Fabric')!
    expect(summary.rows[11]?.[5]).toBe(0)
    expect(summary.rows[12]?.[5]).toBe(0)
    expect(summary.rows[15]?.[5]).toBe(.17)
    expect(summary.rows[11]?.[6]).toBeCloseTo(1.02, 6)
    expect(summary.rows[12]?.[6]).toBeCloseTo(2.04, 6)
    expect(fabric.rows[7]?.[7]).toBe(.02)
    expect(fabric.rows[8]?.[7]).toBe(0)
    expect(summary.rows[32]?.[6]).toBe(summaryData.exFactoryHkd)
  }, 30_000)

  it('converts raw material and machine tariffs once and keeps the template lookup tables in sync', () => {
    const source = artifact('plastic')
    const toolRow = (source.sections.molding.payload.caixing_tool_plan_rows as Array<Record<string, unknown>>)[0]
    toolRow.material_price_hkd_lb = 7.2
    toolRow.machine_daily_hkd = 1000
    toolRow.material_cost_hkd = 0
    toolRow.process_cost_hkd = 0
    ;(source.sections.sales.payload.customer_quote_fields as Record<string, Record<string, unknown>>).caixing.markup_rate_override = .18
    const pricing = caixingPricing()
    const result = convertCaixingP4InternalQuote(source, 'raw.xlsx', pricing)
    const row = result.sheets[0].quoteData.injectionRows[0]
    expect(row.materialUnitPriceHkdKg).toBeCloseTo(7.2 / 454 * 1000 * 1.02, 6)
    expect(row.materialCostHkd).toBeCloseTo(.12 * 7.2 / 454 * 1000 * 1.02 * 1.02, 4)
    expect(row.moldingCostHkd).toBeCloseTo(26 / 3600 * (1000 / 24 / .98) / 2, 4)
    expect(result.sheets[0].quoteData.summary.markupRate).toBe(.18)
    expect(buildCaixingCustomerQuoteFileName(result)).toContain('_V1_')
    const template = readFileSync('public/templates/caixing-plastic-customer-quote-template.bin')
    const output = createCaixingCustomerQuoteWorkbook(result, template)
    const workbook = parseXlsxWorkbook(asArrayBuffer(output), { includeFormulas: true })
    const summary = workbook.sheets.find((sheet) => sheet.name === 'Summary')!
    const toolPlan = workbook.sheets.find((sheet) => sheet.name === 'Tool Plan')!
    expect(summary.rows[10]?.[5]).toBe(.18)
    expect(summary.cellFormulas?.E20).toBe('C20*D20')
    expect(summary.rows[39]?.[5]).toBeCloseTo(row.materialUnitPriceHkdKg!, 5)
    expect(summary.rows[43]?.[7]).toBeCloseTo(row.machineHourlyHkd!, 5)
    expect(toolPlan.rows[13]?.[13]).toBeCloseTo(row.materialCostHkd, 4)
    expect(toolPlan.rows[13]?.[16]).toBeCloseTo(row.moldingCostHkd, 4)
    expect(toolPlan.cellFormulas?.N14).toContain('VLOOKUP(K14,Summary!$C$40:$F$53,4)')
    expect(toolPlan.cellFormulas?.Q14).toContain('VLOOKUP(O14,Summary!$G$40:$H$49,2,FALSE)')
    const firstZip = unzipSync(output)
    const repeatedZip = unzipSync(createCaixingCustomerQuoteWorkbook(result, template))
    expect(Object.keys(repeatedZip)).toEqual(Object.keys(firstZip))
    Object.keys(firstZip).forEach((path) => expect(repeatedZip[path]).toEqual(firstZip[path]))
  }, 30_000)

  it('asks for raw prices when changed conversion factors cannot be applied to manually entered totals', () => {
    const pricing = caixingPricing()
    pricing.rates.material_price_uplift_rate = .03
    expect(() => convertCaixingP4InternalQuote(artifact(), 'missing-raw.xlsx', pricing)).toThrow('缺少内部材料磅价')
    pricing.rates.material_price_uplift_rate = .02
    pricing.rates.machine_utilization_factor = .95
    expect(() => convertCaixingP4InternalQuote(artifact(), 'missing-raw.xlsx', pricing)).toThrow('缺少内部啤机日价')
  })

  it('does not guess a fabric scrap allowance from an unsplit sewing total', () => {
    const source = artifact('plush')
    source.sections.sewing.calculation.totals = { clothes_hkd: 3 }
    expect(() => convertCaixingP4InternalQuote(source, 'sewing-total.xlsx', caixingPricing())).toThrow('缺少逐项材料与人工明细')
  })

  it('uses the approved molding calculation raw prices when a Tool Plan row matches one internal part', () => {
    const source = artifact('plastic')
    source.sections.molding.calculation.line_breakdown = [
      { kind: 'injection', item: '剑柄上盖', mold_no: 'T-01', material: 'ABS', net_weight_g: 120,
        material_price_hkd_lb: 7.2, machine_shift_price_hkd: 1000 },
    ]
    const pricing = caixingPricing()
    pricing.rates.material_price_uplift_rate = .03
    pricing.rates.machine_utilization_factor = .95
    const result = convertCaixingP4InternalQuote(source, 'approved-source.xlsx', pricing)
    expect(result.warnings).toEqual([])
    const row = result.sheets[0].quoteData.injectionRows[0]
    expect(row.materialCostHkd).toBeCloseTo(.12 * 7.2 / 454 * 1000 * 1.03 * 1.02, 4)
    expect(row.moldingCostHkd).toBeCloseTo(26 / 3600 * (1000 / 24 / .95) / 2, 4)
  })

  it('calls out a Tool Plan part that cannot be uniquely tied to approved molding prices', () => {
    const source = artifact('plastic')
    source.sections.molding.calculation.line_breakdown = [
      { kind: 'injection', item: '另一零件', mold_no: 'T-02', material: 'ABS', net_weight_g: 10,
        material_price_hkd_lb: 7.2, machine_shift_price_hkd: 1000 },
    ]
    const result = convertCaixingP4InternalQuote(source, 'unmatched.xlsx', caixingPricing())
    expect(result.warnings?.[0]).toContain('未唯一匹配内部啤机明细')
  })

  it('does not use an injection price for an RC tooling row with the same part name', () => {
    const source = artifact('plush')
    source.sections.molding.calculation.line_breakdown = [
      { kind: 'injection', item: '公仔头', mold_no: 'T-01', material: 'PVC', net_weight_g: 7,
        material_price_hkd_lb: 7.2, machine_shift_price_hkd: 1000 },
    ]
    const result = convertCaixingP4InternalQuote(source, 'rc.xlsx', caixingPricing())
    const row = result.sheets[0].quoteData.injectionRows[0]
    expect(row.materialUnitPriceHkdKg).toBeUndefined()
    expect(row.machineHourlyHkd).toBeUndefined()
    expect(row.materialCostHkd).toBe(.125)
    expect(row.moldingCostHkd).toBe(.36)
    expect(result.warnings?.[0]).toContain('未唯一匹配内部啤机明细')
  })

  it('blocks a Tool Plan row whose SKU differs from this quote item', () => {
    const source = artifact('plastic')
    ;(source.sections.molding.payload.caixing_tool_plan_rows as Array<Record<string, unknown>>)[0].sku_no = '68972'
    expect(() => convertCaixingP4InternalQuote(source, 'wrong-sku.xlsx')).toThrow('SKU No. 与本单 Item No. 不一致')
  })

  it('flags sample-specific layouts that are not yet represented by the two base templates', () => {
    const source = artifact('plastic')
    ;(source.sections.sales.payload.customer_quote_fields as Record<string, Record<string, unknown>>).caixing.item_number = '68972'
    ;(source.sections.molding.payload.caixing_tool_plan_rows as Array<Record<string, unknown>>)[0].sku_no = '68972'
    const result = convertCaixingP4InternalQuote(source, '68972.xlsx')
    expect(result.warnings).toEqual([expect.stringContaining('独立行位与说明区')])
  })

  it('requires an integer material code before generating spreadsheet references', () => {
    const source = artifact('plastic')
    ;(source.sections.molding.payload.caixing_tool_plan_rows as Array<Record<string, unknown>>)[0].material_code = 1.5
    expect(() => convertCaixingP4InternalQuote(source, 'fractional-code.xlsx')).toThrow('Material Code 必须是 1 至 14 的整数')
  })

  it('blocks manual amounts that a shared material or machine rate cannot recalculate', () => {
    const source = artifact('plastic')
    const rows = source.sections.molding.payload.caixing_tool_plan_rows as Array<Record<string, unknown>>
    rows.push({ ...rows[0], ref_no: '2', tool_no: 'T-02', tooling_cost_hkd: 0, material_cost_hkd: 1.99 })
    const template = readFileSync('public/templates/caixing-plastic-customer-quote-template.bin')
    const changedMaterial = convertCaixingP4InternalQuote(source, 'changed-material.xlsx')
    expect(() => createCaixingCustomerQuoteWorkbook(changedMaterial, template)).toThrow('料金额与材料编号 1 共用单价重算不一致')
    rows[1].material_cost_hkd = 1.98
    rows[1].process_cost_hkd = .23
    const changedProcess = convertCaixingP4InternalQuote(source, 'changed-process.xlsx')
    expect(() => createCaixingCustomerQuoteWorkbook(changedProcess, template)).toThrow('啤工与机型 14 共用小时价重算不一致')
  })

  it('writes the current material name next to its customer material code', () => {
    const source = artifact('plastic')
    const toolRow = (source.sections.molding.payload.caixing_tool_plan_rows as Array<Record<string, unknown>>)[0]
    toolRow.material_code = 3
    toolRow.material = 'C-ABS'
    toolRow.material_price_hkd_lb = 7.2
    toolRow.machine_size = '18'
    toolRow.machine_daily_hkd = 1000
    const result = convertCaixingP4InternalQuote(source, 'material-code.xlsx', caixingPricing())
    const output = createCaixingCustomerQuoteWorkbook(result, readFileSync('public/templates/caixing-plastic-customer-quote-template.bin'))
    const workbook = parseXlsxWorkbook(asArrayBuffer(output), { includeFormulas: true })
    const summary = workbook.sheets.find((sheet) => sheet.name === 'Summary')!
    const toolPlan = workbook.sheets.find((sheet) => sheet.name === 'Tool Plan')!
    expect(summary.rows[41]?.[3]).toBe('C-ABS')
    expect(summary.rows.slice(39, 49).some((row) => row?.[6] === 18 && Math.abs(Number(row?.[7]) - 1000 / 24 / .98) < .001)).toBe(true)
    expect(toolPlan.cellFormulas?.Q14).toContain('VLOOKUP(O14,Summary!$G$40:$H$49,2,FALSE)')
  })

  it('keeps the original picture anchors for the current product and removes sample product media', () => {
    const template = readFileSync('public/templates/caixing-plastic-customer-quote-template.bin')
    const result = convertCaixingP4InternalQuote(artifact(), 'image.xlsx')
    const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/lXcAAAAASUVORK5CYII=', 'base64')
    result.sheets[0].quoteData.image = { bytes: png, extension: 'png' }
    const zip = unzipSync(createCaixingCustomerQuoteWorkbook(result, template))
    expect(Array.from(zip['xl/media/caixing-product.png']!)).toEqual(Array.from(png))
    expect(zip['xl/media/image1.png']).toBeUndefined()
    expect(zip['xl/media/image2.png']).toBeUndefined()
    expect(zip['xl/media/image3.png']).toBeUndefined()
    expect(zip['xl/media/image4.png']).toBeDefined()
    const deco = strFromU8(zip['xl/drawings/drawing1.xml']!)
    const summary = strFromU8(zip['xl/drawings/drawing2.xml']!)
    expect((deco.match(/<xdr:pic>/g) || []).length).toBe(3)
    expect((summary.match(/<xdr:pic>/g) || []).length).toBe(4)
    expect(strFromU8(zip['xl/drawings/_rels/drawing1.xml.rels']!)).toContain('caixing-product.png')
    const withoutImage = convertCaixingP4InternalQuote(artifact(), 'no-image.xlsx')
    const cleanZip = unzipSync(createCaixingCustomerQuoteWorkbook(withoutImage, template))
    expect((strFromU8(cleanZip['xl/drawings/drawing1.xml']!).match(/<xdr:pic>/g) || []).length).toBe(0)
    expect((strFromU8(cleanZip['xl/drawings/drawing2.xml']!).match(/<xdr:pic>/g) || []).length).toBe(1)
  }, 30_000)

  it('extends the plastic Tool Plan without dropping the 68972-size part list', () => {
    const source = artifact('plastic')
    const toolRows = source.sections.molding.payload.caixing_tool_plan_rows as Array<Record<string, unknown>>
    for (let index = 2; index <= 61; index += 1) {
      toolRows.push({ ...toolRows[0], ref_no: String(index), tool_no: '', tooling_cost_hkd: 0,
        description: `Part ${index}`, up: 1, cavities: 1, net_weight_g: 10,
        material_cost_hkd: .165, process_cost_hkd: .458 })
    }
    const result = convertCaixingP4InternalQuote(source, 'many-parts.xlsx', caixingPricing())
    const output = createCaixingCustomerQuoteWorkbook(result, readFileSync('public/templates/caixing-plastic-customer-quote-template.bin'))
    const workbook = parseXlsxWorkbook(asArrayBuffer(output), { includeFormulas: true })
    const tool = workbook.sheets.find((sheet) => sheet.name === 'Tool Plan')!
    const summary = workbook.sheets.find((sheet) => sheet.name === 'Summary')!
    expect(tool.rows[75]?.[5]).toBe('Part 61')
    expect(tool.rows[76]?.[13]).toBeCloseTo(.165 * 17, 4)
    expect(tool.rows[77]?.[13]).toBeCloseTo(result.sheets[0].quoteData.summary.material.plasticParts, 4)
    expect(tool.cellFormulas?.N77).toBe('SUM(N60:N76)')
    expect(tool.cellFormulas?.N78).toBe('N58+N77')
    expect(summary.cellFormulas?.E11).toBe("'Tool Plan'!N78")
    const zip = unzipSync(output)
    expect(strFromU8(zip['xl/workbook.xml']!)).toContain("'Tool Plan'!$A$1:$Q$78")
    const toolXml = strFromU8(zip['xl/worksheets/sheet3.xml']!)
    const rowStyle = (number: number) => toolXml.match(new RegExp(`<c\\b[^>]*r="A${number}"[^>]*s="(\\d+)"`))?.[1]
    expect(rowStyle(76)).toBe(rowStyle(67))
  }, 30_000)
})
