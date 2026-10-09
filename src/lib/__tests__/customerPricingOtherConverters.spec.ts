import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { strFromU8, strToU8, unzipSync, zipSync } from 'fflate'
import { createXlsxWorkbook, parseXlsxWorkbook, type XlsxCellInput } from '../customerPriceConverters/xlsxLite'
import { convertDisneyInternalQuote, createDisneyCustomerQuoteWorkbook } from '../customerPriceConverters/disney'
import { convertCaixingInternalQuote, createCaixingCustomerQuoteWorkbook } from '../customerPriceConverters/caixing'
import { convertThreeSixtyInternalQuote, convertThreeSixtyP4InternalQuote, createThreeSixtyCustomerQuoteWorkbook } from '../customerPriceConverters/threeSixty'
import { convertDickieV2, combineDickieV2, createDickieV2Workbook } from '../customerPriceConverters/dickieV2'
import { createDickieMapping } from '../dickieQuote'
import { P4_SECTION_CODES, P4_ARTIFACT_TEMPLATE_VERSION, P4_STRUCTURED_DATA_SCHEMA_VERSION, type P4InternalQuoteArtifact, type P4SectionCode } from '../customerPriceConverters/p4Artifact'
import type { CustomerPricingSettings } from '../customerPriceConverters/pricingSettings'

const defaults = JSON.parse(readFileSync('shared/customerPriceDefaults.json', 'utf8'))
function settings(customer: string, rates: Record<string, number> = {}): CustomerPricingSettings {
  const d = defaults[customer]
  return { factory_id: d.factoryId, customer_id: customer, revision: 1, snapshot_id: customer + '-snapshot',
    materials: structuredClone(d.materials), rates: { ...Object.fromEntries(Object.entries(d.rates).map(([key, row]) => [key, (row as {value:number}).value])), ...rates }, texts: {}, updated_at: '', updated_by_name: '' }
}
function asArrayBuffer(bytes: Uint8Array) { return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer }
function sheetXml(bytes: Uint8Array, index = 1) { return strFromU8(unzipSync(bytes)[`xl/worksheets/sheet${index}.xml`]!) }
function cell(xml: string, ref: string) { return xml.match(new RegExp('<c\\b[^>]*r="'+ref+'"[^>]*>[\\s\\S]*?</c>'))?.[0] ?? '' }

function createMinimalDisneyWorkbook() {
  const detailRows: XlsxCellInput[][] = Array.from({ length: 66 }, () => [])

  detailRows[0][2] = '料型'
  detailRows[0][3] = 'ABS料'
  detailRows[1][2] = '单价/P'
  detailRows[1][3] = 7.5
  detailRows[2][3] = 2.16
  detailRows[6][2] = '机型'
  detailRows[6][3] = '14A'
  detailRows[7][2] = '单价/元'
  detailRows[7][3] = 1490
  detailRows[8][3] = 8.12
  detailRows[9][0] = '#1000142435 Indiana Jones Pul-back Ride Vehicle 报价（图纸评估报价）'
  detailRows[10][2] = '名称'
  detailRows[10][3] = '料型（Part Material）'
  detailRows[10][4] = '料重(G)'
  detailRows[10][6] = '机型(A)'
  detailRows[10][7] = '1出幾套'
  detailRows[10][8] = '啤數'
  detailRows[10][9] = '啤工'
  detailRows[10][10] = '料金额'
  detailRows[10][12] = '周期（Cycle Time (s)'
  detailRows[10][14] = 'Press size (TON)'
  detailRows[11][1] = 1
  detailRows[11][2] = '车面'
  detailRows[11][3] = 'ABS'
  detailRows[11][4] = 28
  detailRows[11][5] = 0.01652
  detailRows[11][6] = '14A'
  detailRows[11][7] = 1
  detailRows[11][8] = 2200
  detailRows[11][9] = 0.677
  detailRows[11][10] = 0.462
  detailRows[11][12] = 39
  detailRows[11][13] = 0.0605
  detailRows[11][14] = 999
  for (const [rowIndex, lineNo, description, machine] of [
    [12, 2, '档风玻璃', '18A'],
    [13, 3, '车轮', '7A'],
    [14, 4, '公子/公子鼻子', '7A'],
  ] as const) {
    detailRows[rowIndex][1] = lineNo
    detailRows[rowIndex][2] = description
    detailRows[rowIndex][3] = 'ABS'
    detailRows[rowIndex][4] = 28
    detailRows[rowIndex][5] = 0.01652
    detailRows[rowIndex][6] = machine
    detailRows[rowIndex][7] = 1
    detailRows[rowIndex][8] = 2200
    detailRows[rowIndex][9] = 0.677
    detailRows[rowIndex][10] = 0.462
    detailRows[rowIndex][12] = 39
    detailRows[rowIndex][13] = 0.0605
    detailRows[rowIndex][14] = 999
  }
  detailRows[24][10] = '裝箱尺碼：'
  detailRows[24][11] = 12.56
  detailRows[24][12] = 10.2
  detailRows[24][13] = 3.76
  detailRows[29][9] = '装箱数'
  detailRows[29][10] = 6
  detailRows[30][1] = '五金'
  detailRows[30][2] = '螺丝M2.6*8PB（6Pcs)'
  detailRows[30][5] = 0.008
  detailRows[31][1] = '其他外购'
  detailRows[31][2] = '回力牙箱（1PCS)'
  detailRows[31][5] = 0.077
  detailRows[32][1] = '纸箱'
  detailRows[32][2] = '外箱 （B=B）'
  detailRows[32][5] = 0.05
  detailRows[33][1] = '其他外购'
  detailRows[33][2] = '封箱胶纸/胶水/雪梨纸'
  detailRows[33][5] = 0.013
  detailRows[34][1] = '装配工'
  detailRows[34][2] = '半成品（23人/11H/2000)'
  detailRows[34][5] = 0.12
  detailRows[35][1] = '装配工'
  detailRows[35][2] = '包装装配工（22人/11H/3000）'
  detailRows[35][5] = 0.1
  detailRows[36][1] = '彩盒/内咭'
  detailRows[36][2] = 'PDQ'
  detailRows[36][3] = 0.47
  detailRows[36][5] = 0.061
  detailRows[37][1] = '其他外购'
  detailRows[37][2] = '车面贴纸'
  detailRows[37][3] = 0.57
  detailRows[37][5] = 0.075
  detailRows[38][1] = '彩盒/内咭'
  detailRows[38][2] = '吊牌'
  detailRows[38][3] = 0.32
  detailRows[38][5] = 0.042
  detailRows[39][1] = '其他外购'
  detailRows[39][2] = '胶膜（防碰花）'
  detailRows[39][3] = 0.1
  detailRows[39][5] = 0.013
  detailRows[40][1] = '彩盒/内咭'
  detailRows[40][2] = '吊牌'
  detailRows[40][5] = 11794.845
  detailRows[40][6] = 83705.35
  detailRows[40][7] = 129362.81
  detailRows[44][2] = '3K报价：'
  detailRows[46][2] = '包含测试费用（US)：'
  detailRows[46][3] = 3.04
  detailRows[46][4] = 3.11
  detailRows[46][5] = 3.08
  detailRows[46][6] = 3.07
  detailRows[46][7] = 3.07
  detailRows[46][8] = 3.06
  detailRows[46][9] = 3.06
  detailRows[47][5] = 0.027
  detailRows[51][2] = '5K报价：'
  detailRows[53][2] = '包含测试费用（US)：'
  detailRows[53][3] = 2.81
  detailRows[53][4] = 2.87
  detailRows[53][5] = 2.84
  detailRows[53][6] = 2.84
  detailRows[53][7] = 2.84
  detailRows[53][8] = 2.83
  detailRows[53][9] = 2.83
  detailRows[58][2] = '10K报价：'
  detailRows[60][2] = '包含测试费用（US)：'
  detailRows[60][3] = 2.62
  detailRows[60][4] = 2.69
  detailRows[60][5] = 2.66
  detailRows[60][6] = 2.66
  detailRows[60][7] = 2.65
  detailRows[60][8] = 2.65
  detailRows[60][9] = 2.64
  detailRows[62][9] = 'MOQ:'
  detailRows[62][10] = 3000

  const moldRows: XlsxCellInput[][] = Array.from({ length: 4 }, () => [])
  moldRows[0][1] = 'Mold #'
  moldRows[0][2] = 'Parts (膠件)'
  moldRows[0][5] = 'Resin'
  moldRows[0][6] = 'Cav.'
  moldRows[0][7] = 'Up'
  moldRows[0][11] = 'USD'
  moldRows[1][1] = 'M01'
  moldRows[1][2] = '车面'
  moldRows[1][5] = 'ABS'
  moldRows[1][6] = 1
  moldRows[1][7] = 1
  moldRows[1][10] = 1111
  moldRows[1][11] = 8900

  const sprayRows: XlsxCellInput[][] = Array.from({ length: 30 }, () => [])
  sprayRows[28][8] = 34
  sprayRows[28][10] = 0.0171

  const modelRows: XlsxCellInput[][] = Array.from({ length: 16 }, () => [])
  modelRows[12][3] = '画图'
  modelRows[12][9] = 1500
  modelRows[13][3] = '功能色板'
  modelRows[13][9] = 3800
  modelRows[14][3] = '开模板'
  modelRows[14][9] = 2400

  return applyMoqHighlightFills(asArrayBuffer(createXlsxWorkbook([
    { name: '明细', rows: detailRows },
    { name: '喷油报价', rows: sprayRows },
    { name: '模具报价', rows: moldRows },
    { name: '手办报价', rows: modelRows },
  ])), ['F47', 'G54', 'J61'])
}

function createMinimalCaixingWorkbook() {
  const rows: XlsxCellInput[][] = Array.from({ length: 90 }, () => [])

  rows[9][0] = '68963发声亮灯剑报价（按图报价）'
  rows[10][2] = '名称'
  rows[10][3] = '料型'
  rows[10][4] = '料重(G)'
  rows[10][6] = '机型(A)'
  rows[10][7] = '1出几套'
  rows[10][8] = '1出几件'
  rows[10][9] = '目标数'
  rows[10][10] = '啤工'
  rows[10][11] = '料金额'
  rows[10][13] = '周期'
  rows[10][14] = '模价'
  rows[10][15] = '报客模费'
  rows[12][1] = '1'
  rows[12][2] = '剑柄上盖'
  rows[12][3] = 'ABS'
  rows[12][4] = 120
  rows[12][6] = 14
  rows[12][7] = 2
  rows[12][8] = 2
  rows[12][9] = 3600
  rows[12][10] = 0.2
  rows[12][11] = 1.94
  rows[12][13] = 24
  rows[12][14] = 5000
  rows[12][15] = 5300
  rows[13][2] = '剑柄下盖'
  rows[13][8] = 2
  rows[14][9] = '合计：'
  rows[14][10] = 0.2
  rows[14][11] = 1.94
  rows[34][1] = '料价'
  rows[34][2] = '料'
  rows[34][3] = 1.94
  rows[35][1] = '啤工'
  rows[35][2] = '啤工'
  rows[35][3] = 0.2
  rows[36][1] = '装配工'
  rows[36][2] = '装配人工'
  rows[36][3] = 0.6
  rows[37][1] = '彩盒/内咭'
  rows[37][2] = '彩盒'
  rows[37][3] = 1.2
  rows[38][1] = '五金'
  rows[38][2] = '螺丝'
  rows[38][3] = 0.08
  rows[39][1] = '车衣'
  rows[39][2] = '衣服'
  rows[39][3] = 1.5
  rows[40][1] = '车发'
  rows[40][2] = '车发人工'
  rows[40][3] = 0.4
  rows[41][12] = '外箱外尺码：'
  rows[41][13] = 13
  rows[41][14] = 11
  rows[41][15] = 9.5
  rows[42][12] = 'CU.FT：'
  rows[42][13] = 0.786
  rows[43][12] = '纸箱价：'
  rows[43][13] = 3.9
  rows[43][14] = 4

  return asArrayBuffer(createXlsxWorkbook([{ name: '68963', rows }]))
}

function threeSixtyArtifact(): P4InternalQuoteArtifact {
  const section = (
    code: P4SectionCode,
    payload: Record<string, unknown>,
    calculation: Record<string, unknown> = {},
  ) => ({
    code,
    name: code,
    status: 'approved',
    revision: 1,
    calculationStatus: 'valid',
    dependencyStatus: 'current',
    calculationHash: `${code}-hash`,
    isRequired: true,
    payload,
    calculation: {
      ...calculation,
      calculation_hash: `${code}-hash`,
      formula_version: 'rr2-2026-v1',
      reference_snapshot_id: 'IQREF-360',
    },
  })
  return {
    templateVersion: 'internal-quote-p4-v2',
    structuredDataSchemaVersion: 'internal-quote-structured-data-v1',
    quoteNo: 'IQ-HKA-360-001',
    versionLabel: 'V1',
    customer: '360',
    quantity: 20_000,
    productName: 'Cuddle Baby',
    factoryAndWorkshop: 'huakang-a/华康 A',
    formulaVersion: 'rr2-2026-v1',
    referenceSnapshotId: 'IQREF-360',
    referenceSnapshot: { fx: { rmb_hkd: .85, hkd_usd: 7.8, rmb_usd: 7.75 } },
    sections: {
      sales: section('sales', {
        testing_fee_total_usd: 4000,
        color_box_size_in: { length: 18.5, width: 6, height: 16 },
        packaging_materials: [
          { item: '彩盒', quantity: 1 },
          { item: '颈吸塑托', quantity: 1 },
        ],
        cartons: [{
          item: 'Master Carton',
          length_in: 24.75,
          width_in: 19.25,
          height_in: 17,
          qty_per_carton: 4,
          flat_cards: [],
        }],
        customer_quote_fields: {
          three_sixty: {
            ms_brand: 'Cuddle Baby',
            prepared_by: '郑大能',
            quote_date: '2026-06-26',
            revision: '0',
            first_etd: '2026-08-01',
            freight_route_key: 'yt40',
          },
        },
      }, {
        line_breakdown: [
          { kind: 'packaging_material', item: '彩盒', quantity: 1, amount_hkd: 11.7 },
          { kind: 'packaging_material', item: '颈吸塑托', quantity: 1, amount_hkd: .36 },
          { kind: 'carton', item: 'Master Carton', carton_price_hkd: 10.4, flat_card_price_hkd: 0, per_piece_hkd: 2.6, cuft: 4.686, qty_per_carton: 4 },
        ],
        totals: {
          packaging_material_hkd: 12.06,
          carton_hkd: 2.6,
          freight_options: [{
            route_key: 'yt40',
            item: '40尺盐田柜',
            total_cartons: 429,
            freight_per_piece_hkd: 4.55,
            lifting_per_piece_hkd: 0,
            per_piece_hkd: 4.55,
          }],
        },
      }),
      engineering: section('engineering', {
        materials: [{ item: '眼珠', quantity: 2 }],
        molds: [{ item: '公仔模', quantity: 1, cost_rmb: 7750 }],
        production_mold_costs: [{ item: '公仔模', cost_rmb: 7750 }],
      }, {
        line_breakdown: [
          { kind: 'material', item: '眼珠', category: 'auxiliary', auxiliary_category: '其他外购', quantity: 2, unit_price_hkd: .7, amount_hkd: 1.4 },
          { kind: 'production_mold_cost', item: '公仔模', amount_rmb: 7750, reference_only: true },
        ],
        totals: {
          total_hkd: 1.4,
          mold_total_rmb: 7750,
          mold_fx_rmb_usd: 7.75,
        },
      }),
      electronic: section('electronic', {}, {
        line_breakdown: [
          { kind: 'electronic_component', item: 'IC', quantity: 1, amount_hkd: 2 },
        ],
        totals: { total_hkd: 2.2 },
      }),
      molding: section('molding', {
        injection_lines: [{
          item: '鞋子',
          cavity: '2',
          sets: 1,
          machine_code: '12A',
          cycle_time_seconds: 24,
        }],
        blow_lines: [{
          item: '吹气身体',
          estimated_weight_g: 50,
          cycle_time_seconds: 40,
        }],
      }, {
        line_breakdown: [
          {
            kind: 'injection',
            item: '鞋子',
            mold_no: 'M-01',
            material: 'ABS',
            grade: '',
            loss_weight_g: 103,
            molding_cost_hkd: .58,
            quantity: 1,
            amount_hkd: 1.64,
            machine_code: '12A',
            sets: 1,
          },
          {
            kind: 'blow',
            item: '吹气身体',
            material: 'PVC',
            grade: '',
            material_cost_hkd: .8,
            labor_hkd: .4,
            burr_hkd: .1,
            profit_multiplier: 1.05,
            quantity: 1,
            amount_hkd: 1.365,
          },
        ],
        totals: { injection_hkd: 1.64, blow_hkd: 1.365, total_hkd: 3.005 },
      }),
      painting: section('painting', { quote_mode: 'quick' }, {
        line_breakdown: [
          { kind: 'painting_quick_paint', item: '喷油油漆', amount_hkd: .39 },
          { kind: 'painting_quick_labor', item: '喷油工', amount_hkd: 1.17 },
        ],
        totals: { total_hkd: 1.56 },
      }),
      slush: section('slush', {}, {
        line_breakdown: [{
          kind: 'slush',
          item: '搪胶头',
          material: 'Roto-PVC',
          weight_g: 100,
          quantity: 1,
          unit_price_hkd: 2.35,
          amount_hkd: 2.35,
        }],
        totals: { total_hkd: 2.35 },
      }),
      sewing: section('sewing', { quote_mode: 'detail' }, {
        line_breakdown: [
          { kind: 'sewing_material', item: '棉布', part: '身体', craft: '车缝', usage: .5, unit_price_rmb: 20, markup: 1, amount_rmb: 10 },
        ],
        totals: { total_hkd: 20 },
      }),
      hair: section('hair', {}, {
        line_breakdown: [{ kind: 'hair', item: '公仔头发', quantity: 1, unit_price_hkd: 2, amount_hkd: 2 }],
        totals: { total_hkd: 2 },
      }),
      assembly: section('assembly', {}, {
        line_breakdown: [
          { kind: 'assembly_process', item: '装眼', category: 'assembly', amount_hkd_pcs: .25 },
          { kind: 'assembly_process', item: '包装', category: 'packaging', amount_hkd_pcs: 6.8 },
        ],
        totals: { assembly_hkd: .25, packaging_hkd: 6.8, total_hkd: 7.05 },
      }),
    },
  }
}

function dickieFixture() {
  const mapping = createDickieMapping()
  Object.assign(mapping, { quote_date: '2026-09-11', revision: 'A', item_number: '203747022', item_name: { zh: '城市巴士', en: 'Volvo City Bus' }, inner_pack: 1,
    customer_carton_enabled: true, customer_carton_cm: { length: 44.5, width: 36.5, height: 40 } })
  Object.assign(mapping.offers[0]!, { label: { zh: '中国正常价', en: 'China normal' }, moq: 5000, route_40: 'hk40', route_20: 'hk20', route_lcl: 'hk5t' })
  const artifact: P4InternalQuoteArtifact = {
    templateVersion: P4_ARTIFACT_TEMPLATE_VERSION, structuredDataSchemaVersion: P4_STRUCTURED_DATA_SCHEMA_VERSION,
    quoteNo: 'D-1', versionLabel: 'V1', customer: 'Dickie', quantity: 5000, productName: '城市巴士', factoryAndWorkshop: 'huaxing/华兴', formulaVersion: 'F1', referenceSnapshotId: 'R1', referenceSnapshot: {}, sections: {} as P4InternalQuoteArtifact['sections'],
    customerMapping: { version: 'dickie-v2', quote_id: 'IQ1', quote_no: 'D-1', version_label: 'V1', customer: 'Dickie', factory_id: 'huaxing', formula_version: 'F1', reference_snapshot_id: 'R1',
      prices: ['hk40', 'hk20', 'hk5t'].map((key, i) => ({ moq: 5000, route_key: key, price_hkd: [24.2, 24.5, 25.1][i], lift_hkd: 0 })) },
  }
  P4_SECTION_CODES.forEach(code => { artifact.sections[code] = { code, name: code, status: 'approved', revision: 1, calculationStatus: 'valid', dependencyStatus: 'current', calculationHash: `${code}-hash`, isRequired: true, payload: {}, calculation: { calculation_hash: `${code}-hash`, formula_version: 'F1', reference_snapshot_id: 'R1' } } })
  artifact.sections.sales.payload = { product_size_in: { length: 10, width: 4, height: 5 }, color_box_size_in: { length: 12, width: 5, height: 7 }, cartons: [{ length_in: 20, width_in: 15, height_in: 15, qty_per_carton: 6 }], shipping: { markup_tiers: [{ moq: 5000, markup_x: 1.16 }] }, customer_quote_fields: { dickie: { mapping } } }
  return { artifact, mapping }
}

describe('customer pricing settings in the other customer converters', () => {
  it('uses Disney labor, PO and capacity settings consistently in costs and formulas', () => {
    const source = createMinimalDisneyWorkbook()
    const original = convertDisneyInternalQuote(source, 'Disney-20260922.xlsx')
    const pricing = settings('disney', { labor_vehicle: 12, labor_figure: 9, labor_minutes: 10, po_rate: .35, capacity_factor: .6 })
    const result = convertDisneyInternalQuote(source, 'Disney-20260922.xlsx', pricing)
    const quote = result.sheets[0]!.quoteData
    expect(quote.laborRows[0]!.totalCostUsd).toBe(2)
    expect(quote.laborRows[1]!.totalCostUsd).toBe(1.5)
    expect(quote.totals.productQuoteUsd).toBeCloseTo(quote.totals.subtotalUsd * 1.35, 9)
    expect(quote.plastics[0]!.weeklyCapacity).toBeCloseTo(original.sheets[0]!.quoteData.plastics[0]!.weeklyCapacity * 2 / 3, 8)
    const output = createDisneyCustomerQuoteWorkbook(result, readFileSync('public/templates/disney-customer-quote-template.bin'))
    const xml = sheetXml(output)
    expect(cell(xml, 'D232')).toContain('<v>0.35</v>')
    expect(cell(xml, 'X19')).toContain('*7*0.6/R19')
    expect(result.pricing).toBe(pricing)
    // A later conversion cannot change an earlier result or its exported rates.
    convertDisneyInternalQuote(source, 'other.xlsx', settings('disney', { po_rate: .7 }))
    expect(sheetXml(createDisneyCustomerQuoteWorkbook(result, readFileSync('public/templates/disney-customer-quote-template.bin')))).toBe(xml)
  })

  it('updates Caixing scrap, markup, exchange and transport without changing source resin costs', () => {
    const source = createMinimalCaixingWorkbook()
    const before = convertCaixingInternalQuote(source, '68963.xlsx', 'plastic').sheets[0]!.quoteData
    const pricing = settings('caixing', { plastic_scrap_rate: .1, plastic_markup_rate: .25, hkd_usd: 8, domestic_freight_rate: 4, fob_freight_rate: 6 })
    const result = convertCaixingInternalQuote(source, '68963.xlsx', 'plastic', pricing)
    const quote = result.sheets[0]!.quoteData
    expect(quote.injectionRows).toEqual(before.injectionRows)
    expect(quote.summary.material.packagingMaterial).toBeCloseTo(before.summary.material.packagingMaterial / 1.02 * 1.1, 4)
    expect(quote.summary.markupRate).toBe(.25)
    expect(quote.summary.exFactoryUsd).toBe(Math.round(quote.summary.exFactoryHkd / 8 * 1000) / 1000)
    expect(quote.summary.domesticTransportationHkd).toBe(.786)
    const output = createCaixingCustomerQuoteWorkbook(result, readFileSync('public/templates/caixing-plastic-customer-quote-template.bin'))
    const summary = parseXlsxWorkbook(asArrayBuffer(output)).sheets.find(s => s.name === 'Summary')!
    expect(summary.rows[55]![7]).toBe(8)
    expect(summary.rows[31]![5]).toBe(4)
    expect(summary.rows[33]![5]).toBe(6)
    const packing = parseXlsxWorkbook(asArrayBuffer(output)).sheets.find(s => s.name === 'Packing')!
    expect(packing.rows[24]![12]).toBe(.1)
    const plush = convertCaixingInternalQuote(source, '68963.xlsx', 'plush', settings('caixing', { plush_markup_rate: .3 }))
    expect(plush.sheets[0]!.quoteData.summary.markupRate).toBe(.3)
    const plushOutput = createCaixingCustomerQuoteWorkbook(plush, readFileSync('public/templates/caixing-plush-customer-quote-template.bin'))
    expect(parseXlsxWorkbook(asArrayBuffer(plushOutput)).sheets.find(s => s.name === 'Summary')!.rows[59]![7]).toBe(7.8)
  })

  it('uses 360 materials and rates once and exports the same frozen values', () => {
    const source = threeSixtyArtifact()
    const before = convertThreeSixtyP4InternalQuote(source, '360.xlsx').sheets[0]!.quoteData
    const pricing = settings('three-sixty', { hkd_usd: 8, scrap_rate: .05, markup_rate: .2 })
    pricing.materials.forEach(row => { row.price *= 2 })
    const result = convertThreeSixtyP4InternalQuote(source, '360.xlsx', pricing)
    const quote = result.sheets[0]!.quoteData
    expect(quote.plasticRows[0]!.unitPriceUsd).toBe(before.plasticRows[0]!.unitPriceUsd * 2)
    expect(quote.materialScrapUsd).toBeCloseTo(quote.materialTotalUsd * .05, 3)
    expect(quote.markupUsd).toBeCloseTo(quote.basicTotalUsd * .2, 3)
    expect(quote.transportationUsd).toBeCloseTo(before.transportationUsd * 7.8 / 8, 3)
    const xml = sheetXml(createThreeSixtyCustomerQuoteWorkbook(result, readFileSync('public/templates/360-customer-quote-template.bin')))
    expect(cell(xml, 'O20')).toContain('<v>8</v>')
    expect(cell(xml, 'M35')).toContain('<v>0.05</v>')
    expect(cell(xml, 'M36')).toContain('<v>0.2</v>')
    expect(cell(xml, 'L35')).toContain('<f>L32*M35</f>')
    expect(cell(xml, 'L36')).toContain('<f>L34*M36</f>')
  })

  it('preserves Dickie approved prices and all compatible snapshot references while rejecting changed configurations', () => {
    const { artifact } = dickieFixture()
    const original = convertDickieV2(artifact, 'Dickie.xlsx')
    const pricing = settings('dicky')
    pricing.materials[0]!.price = 9.9
    const result = convertDickieV2(artifact, 'Dickie.xlsx', pricing)
    expect(result.v2Data!.products[0]!.offers).toEqual(original.v2Data!.products[0]!.offers)
    const sheets = parseXlsxWorkbook(asArrayBuffer(createDickieV2Workbook(result.v2Data!))).sheets
    for (const sheet of sheets) expect(sheet.rows.some(row => row[1] === 'PP' && row[2] === 9.9)).toBe(true)
    const secondArtifact = structuredClone(artifact)
    secondArtifact.customerMapping!.quote_id = 'IQ2'
    const second = convertDickieV2(secondArtifact, 'Dickie2.xlsx', pricing)
    expect(combineDickieV2([result, second]).pricing?.snapshot_id).toBe(pricing.snapshot_id)
    second.pricing = { ...pricing, snapshot_id: 'other' }
    const combined = combineDickieV2([result, second])
    expect(combined.pricing?.snapshot_ids).toEqual([pricing.snapshot_id, 'other'])
    expect(combined.pricing?.snapshot_id).toBe(pricing.snapshot_id)
    expect(combined.v2Data?.pricing).toBe(combined.pricing)
    const thirdArtifact = structuredClone(artifact)
    thirdArtifact.customerMapping!.quote_id = 'IQ3'
    const third = convertDickieV2(thirdArtifact, 'Dickie3.xlsx', { ...pricing, snapshot_id: 'third' })
    expect(combineDickieV2([combined, third]).pricing?.snapshot_ids).toEqual([pricing.snapshot_id, 'other', 'third'])
    second.pricing = { ...pricing, revision: pricing.revision + 1 }
    expect(() => combineDickieV2([result, second])).toThrow(/快照/)
    second.pricing = { ...pricing, materials: pricing.materials.map(row => ({ ...row, price: 1 })) }
    expect(() => combineDickieV2([result, second])).toThrow(/快照/)
  })

  it('rejects customer/factory mismatches at converter entry', () => {
    expect(() => convertDisneyInternalQuote(createMinimalDisneyWorkbook(), 'x.xlsx', settings('dicky'))).toThrow(/厂区/)
    expect(() => convertCaixingInternalQuote(createMinimalCaixingWorkbook(), 'x.xlsx', 'plastic', settings('disney'))).toThrow(/厂区/)
    expect(() => convertThreeSixtyP4InternalQuote(threeSixtyArtifact(), 'x.xlsx', { ...settings('three-sixty'), factory_id: 'huaxing' })).toThrow(/厂区/)
    expect(() => convertDickieV2(dickieFixture().artifact, 'x.xlsx', settings('disney'))).toThrow(/厂区/)
  })
})

function applyMoqHighlightFills(workbook: ArrayBuffer, refs: string[]) {
  const zip = unzipSync(new Uint8Array(workbook))
  const styles = strFromU8(zip['xl/styles.xml'])
  zip['xl/styles.xml'] = strToU8(styles
    .replace('<fills count="2">', '<fills count="3">')
    .replace('</fills><borders', '<fill><patternFill patternType="solid"><fgColor rgb="FFFFFF00"/></patternFill></fill></fills><borders')
    .replace('<cellXfs count="14">', '<cellXfs count="15">')
    .replace('</cellXfs><cellStyles', '<xf numFmtId="166" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyNumberFormat="1"/></cellXfs><cellStyles'))

  let sheetXml = strFromU8(zip['xl/worksheets/sheet1.xml'])
  refs.forEach((ref) => {
    const cellOpenTag = new RegExp(`<c\\b([^>]*\\br="${ref}"[^>]*)>`)
    sheetXml = sheetXml.replace(cellOpenTag, (_full, attributes: string) => `<c${attributes.replace(/\s+s="[^"]*"/, '')} s="14">`)
  })
  zip['xl/worksheets/sheet1.xml'] = strToU8(sheetXml)

  return asArrayBuffer(zipSync(zip))
}

function legacyWorkbook(includeBreakdown = true) {
  const breakdown: XlsxCellInput[][] = Array.from({ length: 175 }, () => [])
  breakdown[6] = [null, null, 'Cuddle Baby']
  breakdown[9] = Array.from({ length: 15 }, (_, index) => index === 14 ? 'Wong Kin On' : null)
  breakdown[11] = Array.from({ length: 15 }, (_, index) => index === 2 ? 'Toy Doll Cuddle Baby' : index === 14 ? 46199 : null)
  breakdown[13] = Array.from({ length: 15 }, (_, index) => index === 14 ? '0' : null)
  breakdown[15] = Array.from({ length: 15 }, (_, index) => index === 14 ? 20_000 : null)
  breakdown[22] = Array.from({ length: 15 }, (_, index) => index === 14 ? 1 : null)
  breakdown[40] = [null, null, 'Testing Cost : US$', null, 4000]
  breakdown[43] = [null, null, 'Tooling Cost : US$', null, 0]

  const internal: XlsxCellInput[][] = Array.from({ length: 73 }, () => [])
  internal[6] = ['Toy Doll Cuddle Baby']
  internal[7] = [null, null, '名称', '料型', '料重(G)', '料价(G)', '机型(A)', '1出几套', '目标数', '啤工', '料金额']
  internal[8] = ['¥13%', 'PVC', '鞋子', 'PVC', 70.5, .0149, '12A', 1, 2000, .58, 1.0559]
  internal[13] = [null, null, null, '出厂价', "40'盐田柜", "20'盐田柜", '盐田散']
  internal[14] = [null, '装工', '装公仔眼睛', .2553]
  internal[15] = [null, '装工', '包装人工', 6.89]
  internal[16] = ['¥13%', '周总-4', '公仔喷油油漆', .3925]
  internal[17] = [null, '喷油工', '公仔喷油人工', 1.1775]
  internal[18] = [null, '郑副总-2', '搪胶头(100g/pcs）', 2.354]
  internal[19] = ['¥13%', '陈总-5', '眼珠(TEC11)/对', 1.3529]
  internal[20] = [null, '车衣', '粉色连衣裙', 19.18]
  internal[21] = [.13, '周总-1', '彩盒', 11.5412]
  internal[22] = [null, '郑副总-3', '颈吸塑托/1pcs', .36]
  internal[23] = [null, '纸箱', '外箱', 2.6307]
  internal[24] = [null, '运费', null, null, 4.5553, 6.5245, 13.4702]
  internal[29] = [null, null, null, null, null, null, null, null, null, null, null, '彩盒尺寸：', 18.5, 6, 16]
  internal[30] = [null, null, null, null, null, null, null, null, null, null, null, '外箱外尺码：', 24.75, 19.25, 17]
  internal[31] = [null, null, null, null, null, null, null, null, null, null, null, 'CU.FT：', 4.687]
  internal[32] = [null, null, null, null, null, null, null, null, null, null, null, '纸箱价：', 10.5229, 4, 'pcs/ctn']
  internal[33] = [null, null, null, null, null, null, null, null, null, null, null, '每柜数量：', 1717.82, 'pcs']

  return asArrayBuffer(createXlsxWorkbook([
    ...(includeBreakdown ? [{ name: 'Breakdown', rows: breakdown }] : []),
    { name: '内部明细 (Winbow box)', rows: internal },
    { name: '彩盒', rows: [] },
    { name: '车衣', rows: [] },
    { name: '连衣裙 (6.21更新)', rows: [] },
  ]))
}

describe('360 resin maintenance preserves independently derived molding labor', () => {
  it.each(['p4', 'legacy'] as const)('keeps slush labor independent from resin prices for %s inputs', (format) => {
    const convert = (pricing: CustomerPricingSettings) => format === 'p4'
      ? convertThreeSixtyP4InternalQuote(threeSixtyArtifact(), '360.xlsx', pricing)
      : convertThreeSixtyInternalQuote(legacyWorkbook(), '360.xlsx', pricing)
    const baseline = settings('three-sixty')
    const before = convert(baseline).sheets[0]!.quoteData
    const changed = structuredClone(baseline)
    changed.materials.find(row => row.material === 'Roto-PVC')!.price *= 2
    const after = convert(changed).sheets[0]!.quoteData
    const originalSlush = before.plasticRows.find(row => row.machine === 'RC')!
    const changedSlush = after.plasticRows.find(row => row.machine === 'RC')!
    expect(changedSlush.totalUsd).toBeCloseTo(originalSlush.totalUsd * 2, 4)
    expect(changedSlush.moldingUsd).toBe(originalSlush.moldingUsd)
    expect(after.laborTotalUsd).toBe(before.laborTotalUsd)
    expect(after.exFactoryUsd).toBeGreaterThan(before.exFactoryUsd)
    changed.rates.hkd_usd = 8
    const newFxSlush = convert(changed).sheets[0]!.quoteData.plasticRows.find(row => row.machine === 'RC')!
    expect(newFxSlush.totalUsd).toBe(changedSlush.totalUsd)
    expect(newFxSlush.moldingUsd).toBeCloseTo(originalSlush.moldingUsd * 7.8 / 8, 3)
  })
})
