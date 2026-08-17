import { readFileSync } from 'node:fs'
import { strFromU8, unzipSync } from 'fflate'
import { describe, expect, it } from 'vitest'
import {
  THREE_SIXTY_LEGACY_DEFAULT_MOQ,
  THREE_SIXTY_MATERIAL_PRICES_USD_KG,
  convertThreeSixtyInternalQuote,
  convertThreeSixtyP4InternalQuote,
  createThreeSixtyCustomerQuoteWorkbook,
} from '@/lib/customerPriceConverters/threeSixty'
import {
  P4_ARTIFACT_TEMPLATE_VERSION,
  P4_SECTION_CODES,
  P4_STRUCTURED_DATA_SCHEMA_VERSION,
  type P4InternalQuoteArtifact,
  type P4SectionCode,
} from '@/lib/customerPriceConverters/p4Artifact'
import {
  createXlsxWorkbook,
  parseXlsxWorkbook,
  type XlsxCellInput,
} from '@/lib/customerPriceConverters/xlsxLite'

function asArrayBuffer(bytes: Uint8Array) {
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
}

function artifact(): P4InternalQuoteArtifact {
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

function p4Workbook(source: P4InternalQuoteArtifact) {
  const summary: XlsxCellInput[][] = Array.from({ length: 6 }, () => [])
  summary[1] = ['报价编号', source.quoteNo, '版本', source.versionLabel, '客户', source.customer, '数量', source.quantity]
  summary[2] = ['产品', source.productName, '厂区/车间', source.factoryAndWorkshop, '公式版本', source.formulaVersion, '参考快照', source.referenceSnapshotId]

  const approval: XlsxCellInput[][] = Array.from({ length: 8 }, () => [])
  approval[1] = ['模板版本', P4_ARTIFACT_TEMPLATE_VERSION, '公式版本', source.formulaVersion]
  approval[2] = ['参考快照', source.referenceSnapshotId, '报价头revision', 1]
  approval[3] = ['导出阶段', 'P4 最终业务放行']
  approval[4] = ['边界说明', '最终业务放行完成，可交接客价转换台']

  const structured: XlsxCellInput[][] = Array.from({ length: 4 }, () => [])
  structured[1] = ['结构版本', P4_STRUCTURED_DATA_SCHEMA_VERSION]
  structured[2] = ['记录类型', '分段代码', '分段名称', '状态', 'revision', '计算状态', '依赖状态', '计算hash', '分片序号', '分片总数', 'JSON分片', '是否参与']
  const addRecord = (
    recordType: string,
    code: string,
    name: string,
    value: Record<string, unknown>,
    section?: P4InternalQuoteArtifact['sections'][P4SectionCode],
  ) => {
    structured.push([
      recordType,
      code,
      name,
      section?.status ?? 'approved',
      section?.revision ?? 1,
      section?.calculationStatus ?? 'valid',
      section?.dependencyStatus ?? 'current',
      section?.calculationHash ?? '',
      1,
      1,
      JSON.stringify(value),
      section?.isRequired === false ? '否' : '是',
    ])
  }
  addRecord('reference_snapshot', 'quote', '报价参考快照', source.referenceSnapshot)
  P4_SECTION_CODES.forEach((code) => {
    const section = source.sections[code]
    addRecord('payload', code, section.name, section.payload, section)
    addRecord('calculation', code, section.name, section.calculation, section)
  })

  return asArrayBuffer(createXlsxWorkbook([
    { name: '报价明细', rows: summary },
    { name: '审批与版本', rows: approval },
    { name: '结构化数据', rows: structured },
  ]))
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

describe('360 P4 customer converter', () => {
  it('uses the fixed 360 material table, server freight and fixed 2%/12% quotation basis', () => {
    const result = convertThreeSixtyP4InternalQuote(artifact(), 'IQ-HKA-360-001.xlsx')
    const data = result.sheets[0].quoteData
    expect(data.plasticRows).toHaveLength(3)
    expect(data.plasticRows[0]).toMatchObject({
      description: '鞋子',
      material: 'ABS',
      totalWeightG: 103,
      unitPriceUsd: THREE_SIXTY_MATERIAL_PRICES_USD_KG.ABS,
    })
    expect(data.plasticRows[0].totalUsd).toBeCloseTo(.20909, 5)
    expect(data.plasticRows[1].unitPriceUsd).toBe(THREE_SIXTY_MATERIAL_PRICES_USD_KG.PVC)
    expect(data.plasticRows[2].unitPriceUsd).toBe(THREE_SIXTY_MATERIAL_PRICES_USD_KG['Roto-PVC'])
    expect(data.electronicRows[0].totalUsd).toBeCloseTo(2.2 / 7.8, 6)
    expect(data.packagingRows.map((row) => row.description)).toEqual(['彩盒', '颈吸塑托'])
    expect(data.carton).toMatchObject({
      lengthIn: 24.75,
      widthIn: 19.25,
      heightIn: 17,
      qtyPerCarton: 4,
      cartonPriceHkd: 10.4,
      perPieceHkd: 2.6,
    })
    expect(data.transportationUsd).toBeCloseTo(4.55 / 7.8, 6)
    expect(data.materialScrapUsd).toBeCloseTo(data.materialTotalUsd * .02, 6)
    expect(data.markupUsd).toBeCloseTo(data.basicTotalUsd * .12, 6)
    expect(data.testingPerUnitUsd).toBe(.2)
    expect(data.toolingTotalUsd).toBe(1000)
    expect(data.toolingPerUnitUsd).toBe(.05)
    expect(data.metadata.quantityPerContainer).toBe(1700)
  })

  it('omits a preserved testing fee when testing-fee calculation is disabled', () => {
    const source = artifact()
    source.sections.sales!.payload.testing_fee_enabled = false
    const result = convertThreeSixtyP4InternalQuote(source, 'IQ-HKA-360-001.xlsx')
    expect(result.sheets[0].quoteData.testingPerUnitUsd).toBe(0)
  })

  it('outputs only the sanitized Breakdown sheet with auditable same-sheet formulas', () => {
    const result = convertThreeSixtyP4InternalQuote(artifact(), 'IQ-HKA-360-001.xlsx')
    const template = readFileSync('public/templates/360-customer-quote-template.bin')
    const output = createThreeSixtyCustomerQuoteWorkbook(result, template)
    const workbook = parseXlsxWorkbook(asArrayBuffer(output))
    expect(workbook.sheets.map((sheet) => sheet.name)).toEqual(['Breakdown'])
    const breakdown = workbook.sheets[0]
    expect(breakdown.rows[11]?.[2]).toBe('Cuddle Baby')
    expect(breakdown.rows[9]?.[14]).toBe('郑大能')
    expect(breakdown.rows[59]?.[1]).toBe('鞋子')
    expect(breakdown.rows[59]?.[4]).toBe('ABS')
    expect(breakdown.rows[70]?.[7]).toBe(3)
    expect(breakdown.rows[70]?.[8]).toBe(253)
    expect(breakdown.rows[53]?.[0]).toContain('12 40HQ containers')
    expect(breakdown.rows[53]?.[0]).not.toContain('18,700')
    expect(breakdown.rows[132]?.[1]).toBe('彩盒')
    expect(breakdown.rows[137]?.[1]).toBe('Master Carton')
    expect(breakdown.rows[137]?.[6]).toBe(24.75)
    expect(breakdown.rows[137]?.[8]).toBe(19.25)
    expect(breakdown.rows[137]?.[9]).toBe(17)
    expect(breakdown.rows[137]?.[10]).toBe(4)
    expect(breakdown.rows[157]?.[15]).toBeCloseTo(result.sheets[0].quoteData.laborUsd.molding, 6)

    const zip = unzipSync(output)
    expect(Object.keys(zip).filter((path) => /^xl\/worksheets\/sheet\d+\.xml$/.test(path))).toEqual(['xl/worksheets/sheet1.xml'])
    expect(zip['xl/sharedStrings.xml']).toBeUndefined()
    expect(Object.keys(zip).some((path) => path.startsWith('xl/externalLinks/'))).toBe(false)
    const packageText = Object.entries(zip)
      .filter(([path]) => path.endsWith('.xml') || path.endsWith('.rels'))
      .map(([, value]) => strFromU8(value))
      .join('\n')
    expect(packageText).not.toMatch(/内部明细|车衣|连衣裙|Winbow box|#REF!|#NAME\?/)
    expect(packageText).toContain('<f>SUM(L26:L31)</f>')
    expect(packageText).toContain('<f>L138*O138</f>')
  })

  it('accepts a downloaded P4 workbook through the visible Excel import path', () => {
    const result = convertThreeSixtyInternalQuote(
      p4Workbook(artifact()),
      'IQ-HKA-360-001_P4.xlsx',
    )

    expect(result.sourceFileName).toBe('IQ-HKA-360-001_P4.xlsx')
    expect(result.sheets).toHaveLength(1)
    expect(result.sheets[0].name).toBe('Breakdown')
    expect(result.sheets[0].quoteData.metadata).toMatchObject({
      productName: 'Cuddle Baby',
      preparedBy: '郑大能',
      quantity: 20_000,
    })
  })

  it('accepts the original 360 multi-sheet workbook and applies the customer rules', () => {
    const result = convertThreeSixtyInternalQuote(
      legacyWorkbook(),
      'Toy Doll Cuddle Baby Mommy and Me BOM.xlsx',
    )
    const data = result.sheets[0].quoteData

    expect(data.metadata).toMatchObject({
      productName: 'Toy Doll Cuddle Baby',
      preparedBy: 'Wong Kin On',
      quoteDate: '2026-06-26',
      quantity: 20_000,
      containerType: '40HQ',
      quantityPerContainer: 1700,
    })
    expect(data.plasticRows.map((row) => row.description)).toEqual(['鞋子', '搪胶头'])
    expect(data.plasticRows[0]).toMatchObject({
      material: 'PVC',
      partWeightG: 70.5,
      unitPriceUsd: THREE_SIXTY_MATERIAL_PRICES_USD_KG.PVC,
    })
    expect(data.purchaseRows[0]).toMatchObject({ description: '眼珠(TEC11)/对', usage: 2 })
    expect(data.fabricRows[0].description).toBe('粉色连衣裙')
    expect(data.packagingRows.map((row) => row.description)).toEqual(['彩盒', '颈吸塑托/1pcs'])
    expect(data.otherRows[0].description).toBe('公仔喷油油漆')
    expect(data.laborUsd).toMatchObject({
      spray: expect.closeTo(1.1775 / 7.8, 6),
      assembly: expect.closeTo(.2553 / 7.8, 6),
      packing: expect.closeTo(6.89 / 7.8, 6),
    })
    expect(data.carton).toMatchObject({
      lengthIn: 24.75,
      widthIn: 19.25,
      heightIn: 17,
      qtyPerCarton: 4,
      cartonPriceHkd: 10.5229,
      perPieceHkd: 2.6307,
    })
    expect(data.transportationUsd).toBeCloseTo(4.5553 / 7.8, 6)
    expect(data.materialScrapUsd).toBeCloseTo(data.materialTotalUsd * .02, 6)
    expect(data.markupUsd).toBeCloseTo(data.basicTotalUsd * .12, 6)
  })

  it('accepts the daily internal workbook without a Breakdown customer-output sheet', () => {
    const result = convertThreeSixtyInternalQuote(
      legacyWorkbook(false),
      'Toy Doll Cuddle Baby Mommy and Me BOM(2026-6-26）.xlsx',
    )
    const data = result.sheets[0].quoteData

    expect(data.metadata).toMatchObject({
      productName: 'Toy Doll Cuddle Baby',
      preparedBy: '郑大能',
      quoteDate: '2026-06-26',
      quantity: THREE_SIXTY_LEGACY_DEFAULT_MOQ,
      quantityPerContainer: 1700,
    })
    expect(data.plasticRows.map((row) => row.description)).toEqual(['鞋子', '搪胶头'])
    expect(data.carton).toMatchObject({
      lengthIn: 24.75,
      widthIn: 19.25,
      heightIn: 17,
      qtyPerCarton: 4,
    })
  })

  it('blocks data that cannot be mapped truthfully', () => {
    const wrongFactory = artifact()
    wrongFactory.factoryAndWorkshop = 'huaxing/华兴'
    expect(() => convertThreeSixtyP4InternalQuote(wrongFactory, 'wrong.xlsx')).toThrow('仅适用于华康 A')

    const unknownMaterial = artifact()
    const moldingRows = unknownMaterial.sections.molding.calculation.line_breakdown as Array<Record<string, unknown>>
    moldingRows[0].material = 'HIPS'
    expect(() => convertThreeSixtyP4InternalQuote(unknownMaterial, 'unknown.xlsx')).toThrow('固定材料价表未配置')

    const quickSewing = artifact()
    quickSewing.sections.sewing.calculation.line_breakdown = [{ kind: 'sewing_quick', item: '衣服', amount_hkd: 3 }]
    expect(() => convertThreeSixtyP4InternalQuote(quickSewing, 'quick.xlsx')).toThrow('车缝快捷总价不能直接转换')
  })
})
