import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import {
  prepareP4CustomerConversion,
} from '@/lib/customerPriceConverters/p4CustomerAdapter'
import {
  P4_ARTIFACT_TEMPLATE_VERSION,
  P4_SECTION_CODES,
  P4_STRUCTURED_DATA_SCHEMA_VERSION,
  parseP4InternalQuoteArtifact,
  type P4SectionCode,
} from '@/lib/customerPriceConverters/p4Artifact'
import {
  createBuzzBeeCustomerQuoteWorkbook,
} from '@/lib/customerPriceConverters/buzzbee'
import { createDisneyCustomerQuoteWorkbook } from '@/lib/customerPriceConverters/disney'
import { createDickyCustomerQuoteWorkbook } from '@/lib/customerPriceConverters/dicky'
import { strFromU8, unzipSync } from 'fflate'
import {
  createXlsxWorkbook,
  parseXlsxWorkbook,
  type XlsxCellInput,
} from '@/lib/customerPriceConverters/xlsxLite'

function asArrayBuffer(bytes: Uint8Array) {
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer
}

function p4Workbook(
  templateVersion = P4_ARTIFACT_TEMPLATE_VERSION,
  includeCustomerFields = true,
  customer: 'BuzzBee' | '迪士尼' | 'Dickie' = 'BuzzBee',
  inactiveCodes: P4SectionCode[] = [],
  unifiedSummary = false,
) {
  const isDisney = customer === '迪士尼'
  const isDicky = customer === 'Dickie'
  const summary: XlsxCellInput[][] = Array.from({ length: unifiedSummary ? 8 : 6 }, () => [])
  if (unifiedSummary) {
    summary[7] = [isDisney ? 'Indiana Jones Vehicle报价' : isDicky ? 'Disney Cable Car报价' : '火堆套装报价']
  } else {
    summary[1] = ['报价编号', isDisney ? 'IQ-P4-DISNEY-001' : isDicky ? 'IQ-P4-DICKIE-001' : 'IQ-P4-BB-001', '版本', 'V1', '客户', customer, '数量', 3000]
    summary[2] = ['产品', isDisney ? 'Indiana Jones Vehicle' : isDicky ? 'Disney Cable Car' : '火堆套装', '厂区/车间', 'huaxing/华兴', '公式版本', 'rr2-2026-v1', '参考快照', 'IQREF-1']
  }

  const approval: XlsxCellInput[][] = Array.from({ length: 8 }, () => [])
  approval[1] = ['模板版本', templateVersion, '公式版本', 'rr2-2026-v1']
  approval[2] = ['参考快照', 'IQREF-1', '报价头revision', 2]
  approval[3] = ['导出阶段', 'P4 最终业务放行']
  approval[4] = ['边界说明', '最终业务放行完成，可交接客价转换台']

  const structured: XlsxCellInput[][] = Array.from({ length: 4 }, () => [])
  structured[1] = ['结构版本', P4_STRUCTURED_DATA_SCHEMA_VERSION]
  structured[2] = ['记录类型', '分段代码', '分段名称', '状态', 'revision', '计算状态', '依赖状态', '计算hash', '分片序号', '分片总数', 'JSON分片', '是否参与']
  const addRecord = (type: string, code: string, name: string, value: Record<string, unknown>, isRequired = true) => {
    structured.push([type, code, name, isRequired ? 'approved' : 'draft', 2, isRequired ? 'valid' : 'pending', 'current', isRequired ? `${code}-hash` : '', 1, 1, JSON.stringify(value), isRequired ? '是' : '否'])
  }
  addRecord('reference_snapshot', 'quote', '报价参考快照', { fx: { hkd_usd: 7.8 } })
  P4_SECTION_CODES.forEach((code) => {
    const isRequired = !inactiveCodes.includes(code)
    const payload = code === 'molding'
      ? {
          injection_lines: [{
            item: isDisney ? '车面' : '水箱盖', material: isDisney ? 'ABS' : 'LDPE', grade: isDisney ? '750SW' : 'G812', net_weight_g: isDisney ? 28 : 4,
            loss_rate_percent: 3, machine_code: isDisney ? '14A' : unifiedSummary ? '14A-16A' : '18A', sets: 1, target_output: 2800, quantity: 1,
            ...(isDisney ? { disney_mold_no: 'M01', disney_resin_cost_usd_kg: 2.16, disney_cycle_time_seconds: 39, disney_labor_rate_usd_hr: 8.12 } : {}),
          }],
          blow_lines: [],
        }
      : code === 'engineering'
        ? {
            materials: isDisney ? [{ item: '螺丝', category: 'hardware', quantity: 1, unit_price_rmb: 1, disney_description: 'Screw', disney_section: 'product', disney_unit_price_usd: .02, disney_included: 1 }] : [],
            molds: isDisney
              ? [{ item: '车面模', quantity: 1, cost_rmb: 1000, disney_mold_no: 'M01', disney_parts: '车面', disney_material: 'ABS', disney_cavities: 1, disney_parts_per_shot: 1, disney_tool_cost_usd: 8900 }]
              : isDicky
                ? [{ item: '车底模', quantity: 1, cost_rmb: 44100, dickie_project_name_en: '20 307 3001\nStitch Cable Buggy', dickie_mold_no: 'M01', dickie_parts_en: 'Car Bottom', dickie_resin: 'C-ABS', dickie_mold_size: '30*35*30', dickie_mold_material: 'NAK80', dickie_cavities: 16, dickie_parts_per_shot: 8, dickie_mold_cost_hkd: 49000, dickie_remark_en: '' }]
                : [],
            amortization_qty: isDisney ? 3000 : 0, customer_mold_subsidy_usd: 0,
          }
        : code === 'painting' && isDisney
          ? { rows: [{ item: 'Whole Item', operations: { spray: { quantity: 34, unit_price_hkd: .0171 } } }], disney_decorations: [{ application_type: 'Whole Item', rate_per_op_usd: .0171, operations: 34 }] }
        : code === 'assembly' && isDisney
          ? { labor_base_hkd: 310, groups: [{ name: 'Assembly vehicle', category: 'assembly', processes: [{ name: 'Assembly vehicle', persons: 1, teams: 1, production_qty: 1000 }] }] }
        : code === 'sales'
          ? {
              paper_price_factor: 2.75,
              testing_fee_total_usd: 1500,
              testing_fee_moqs: [3000, 5000, 10000],
              freight_calc: {
                enabled: true,
                routes: [
                  { key: 'hk_40', name: 'HK 40 柜', capacity_type: 'container_40', freight_hkd: 8000, lift_fee_hkd: 1200 },
                ],
              },
              shipping: {
                markup_tiers: [
                  { moq: 3000, markup_x: 1.18 },
                  { moq: 5000, markup_x: 1.17 },
                  { moq: 10000, markup_x: 1.15 },
                ],
                selected_markup_moq: 3000,
                misc_ratio: 0.02,
              },
              packaging_materials: isDisney
                ? [{ item: '彩盒', specification: '四彩印刷', category: 'color_box_inner_card', quantity: 1, unit_price_rmb: 1, tax_rate_percent: 10, remark: '', disney_description: 'Color Box', disney_unit_price_usd: .12, disney_included: 1 }]
                : [{ item: '彩盒', specification: '四彩印刷', category: 'color_box_inner_card', quantity: 1, unit_price_rmb: 1, tax_rate_percent: 10, remark: '' }],
              product_size_cm: { length: 12, width: 8, height: 4 },
              color_box_size_cm: { length: 13, width: 9, height: 5 },
              cartons: [{ item: '外箱', length_in: 14, width_in: 9.25, height_in: 23.875, qty_per_carton: 2, flat_cards: [], ...(isDisney ? { disney_unit_price_usd: .062 } : {}) }],
              ...(includeCustomerFields ? { customer_quote_fields: {
                ...(isDisney
                  ? { disney: { item_number: '1000142435', quote_date: '2026-06-03', revision: 0, minimum_order_qty: 3000, moq_prices_usd: { qty_3000: 3.08, qty_5000: 2.84, qty_10000: 2.64 }, transportation_usd: .027, model_cost_usd: 6200, setup_charge_usd: 1500 } }
                  : isDicky
                    ? { dickie: {
                        client_name: 'Simba Dickie toys', quote_date: '2026-05-15', attention: 'Sam', revision: '', from_name: 'Ben / Dickie', project_name_en: 'Disney Cable Car', first_shot_time: '45 Working Days', finish_time: '75 Working Days',
                        product_rows: [{ line_no: 1, item_text_en: '20 307 3001\nStitch Cable Buggy\n(2xAA-LR6 INCLUDED)', units_per_carton: '0/12', carton_cbm: .047, color_box_size_cm: '24*11*12cm', carton_size_cm: '49.8*35.2*27cm', production_moq: '5K-10K', price_40h_hkd: 25.3, price_20h_hkd: 25.7, price_lcl_hkd: 25.8 }],
                        remark_lines: [
                          { line_no: 0, text_en: 'If material cost increases more than 5% or RMB exchange rate increases more than 2%, this quote will be revised.' },
                          ...Array.from({ length: 8 }, (_, index) => ({ line_no: index + 1, text_en: `Dickie quotation term ${index + 1}.` })),
                        ],
                        material_prices_hkd: [{ material: 'PP', price_hkd_lb: 5.8 }, { material: 'C-ABS', price_hkd_lb: 10 }, { material: 'ABS', price_hkd_lb: 7.2 }, { material: 'HIPS', price_hkd_lb: 6.8 }],
                      } }
                    : { buzzbee: { color_box_tiers: [{ quote_price_hkd: 6.7, fsc_price_hkd: 6.9, moq: 'MOQ3000' }, { quote_price_hkd: 5.75, fsc_price_hkd: 5.92, moq: 'MOQ20000' }] } }),
              } } : {}),
            }
        : {}
    const calculation = code === 'molding'
      ? {
          line_breakdown: [{ kind: 'injection', item: '水箱盖', material_cost_hkd: '0.0560', molding_cost_hkd: '0.6750', amount_hkd: '0.7310' }],
          totals: { injection_hkd: '2.8150', blow_hkd: '0.0000', total_hkd: '2.8150' },
        }
      : code === 'engineering'
        ? {
            line_breakdown: isDisney ? [{ kind: 'material', item: '螺丝', category: 'hardware', amount_hkd: '1.1765' }] : [],
            totals: { hardware_hkd: isDisney ? '1.1765' : '0.0000', packaging_hkd: '0.0000', carton_hkd: '0.0000', total_hkd: isDisney ? '1.1765' : '0.0000' },
          }
      : code === 'painting' && isDisney
        ? { line_breakdown: [{ kind: 'painting', item: 'Whole Item', amount_hkd: '0.5814' }], totals: { total_hkd: '0.5814' } }
      : code === 'assembly' && isDisney
        ? { line_breakdown: [{ kind: 'assembly_process', item: 'Assembly vehicle', amount_hkd: '0.3100' }], totals: { assembly_hkd: '0.3100', packaging_hkd: '0.0000', total_hkd: '0.3100' } }
      : code === 'sales'
        ? {
            line_breakdown: [
              { kind: 'packaging_material', owner: 'sales', item: '彩盒', category: 'color_box_inner_card', tax_rate_percent: '10.0000', amount_hkd: '1.1765' },
              { kind: 'carton', owner: 'sales', item: '外箱', per_piece_hkd: '2.3265', cuft: '1.7892' },
            ],
            totals: { packaging_material_hkd: '1.1765', carton_hkd: '2.3265', carton_cuft: '1.7892', total_hkd: '3.5030' },
          }
      : { line_breakdown: [], totals: { total_hkd: '0.0000' } }
    Object.assign(calculation, {
      calculation_hash: `${code}-hash`,
      formula_version: 'rr2-2026-v1',
      reference_snapshot_id: 'IQREF-1',
    })
    addRecord('payload', code, code, payload, isRequired)
    addRecord('calculation', code, code, calculation, isRequired)
  })

  return asArrayBuffer(createXlsxWorkbook([
    { name: '报价明细', rows: summary },
    { name: '审批与版本', rows: approval },
    { name: '结构化数据', rows: structured },
  ]))
}

describe('P4 customer price adapter', () => {
  it('validates P4 v2 structured data and drives the BuzzBee converter', () => {
    const source = p4Workbook()
    const artifact = parseP4InternalQuoteArtifact(source)
    expect(artifact.quoteNo).toBe('IQ-P4-BB-001')
    expect(artifact.sections.molding.payload.injection_lines).toHaveLength(1)

    const prepared = prepareP4CustomerConversion(source, 'IQ-P4-BB-001.xlsx', 'buzzbee')
    expect(prepared.customerId).toBe('buzzbee')
    expect(prepared.result.sheets[0].name).toBe('火堆套装')
    expect(prepared.result.sheets[0].totalCustomerHkd).toBeGreaterThan(0)
    expect(prepared.result.sheets[0].quoteData.injectionRows[0].material).toBe('PE')

    const exported = createBuzzBeeCustomerQuoteWorkbook(prepared.result)
    const exportedSheet = parseXlsxWorkbook(asArrayBuffer(exported)).sheets[0]
    expect(exportedSheet.rows[0][0]).toBe('COST BREAKDOWN SHEET (ROYAL REGENT)')
    const cartonRow = exportedSheet.rows.find((row) => row?.[0] === 'CARTON SIZE')
    expect(cartonRow?.[5]).toBe(3.35)
    expect(cartonRow?.[6]).toBe(3.4505)
  })

  it('reads the unified desk layout from the stable approval manifest and handoff metadata', () => {
    const source = p4Workbook(P4_ARTIFACT_TEMPLATE_VERSION, true, 'BuzzBee', [], true)
    const prepared = prepareP4CustomerConversion(
      source,
      'IQ-P4-BB-UNIFIED.xlsx',
      'buzzbee',
      {
        quoteNo: 'IQ-P4-BB-UNIFIED',
        versionLabel: 'V2',
        customer: 'BuzzBee',
        quantity: 3000,
        productName: '火堆套装',
        formulaVersion: 'rr2-2026-v1',
        referenceSnapshotId: 'IQREF-1',
      },
    )

    expect(prepared.artifact).toMatchObject({
      quoteNo: 'IQ-P4-BB-UNIFIED',
      versionLabel: 'V2',
      customer: 'BuzzBee',
      quantity: 3000,
      productName: '火堆套装',
      formulaVersion: 'rr2-2026-v1',
      referenceSnapshotId: 'IQREF-1',
    })
    expect(prepared.result.sheets[0].productName).toBe('火堆套装')
  })

  it('rejects legacy P4 v1 before one-time consumption', () => {
    expect(() => parseP4InternalQuoteArtifact(p4Workbook('internal-quote-p4-v1')))
      .toThrow('旧 P4 v1 没有完整原始参数')
  })

  it('accepts inactive optional sections without treating their draft state as a release blocker', () => {
    const artifact = parseP4InternalQuoteArtifact(
      p4Workbook(P4_ARTIFACT_TEMPLATE_VERSION, true, 'BuzzBee', ['electronic', 'painting']),
    )
    expect(artifact.sections.electronic).toMatchObject({ isRequired: false, status: 'draft' })
    expect(artifact.sections.painting).toMatchObject({ isRequired: false, calculationStatus: 'pending' })
    expect(artifact.sections.sales.isRequired).toBe(true)
  })

  it('keeps customer-specific incomplete mappings explicit', () => {
    expect(() => prepareP4CustomerConversion(
      p4Workbook(P4_ARTIFACT_TEMPLATE_VERSION, false, '迪士尼'),
      'disney-p4.xlsx',
      'disney',
    ))
      .toThrow('Item Number')
  })

  it('drives the Disney customer template from complete P4-only fields', () => {
    const prepared = prepareP4CustomerConversion(
      p4Workbook(P4_ARTIFACT_TEMPLATE_VERSION, true, '迪士尼'),
      'IQ-P4-DISNEY-001.xlsx',
      'disney',
    )
    expect(prepared.customerId).toBe('disney')
    expect(prepared.result.sheets[0].quoteData.metadata.itemNumber).toBe('1000142435')
    expect(prepared.result.sheets[0].quoteData.plastics[0]).toMatchObject({
      toolNo: '1000142435-01',
      toolCostUsd: 8900,
      cavities: 1,
      up: 1,
      cycleTimeSeconds: 39,
    })
    expect(prepared.result.sheets[0].quoteData.decoRows[0]).toMatchObject({ applicationType: 'Whole Item', operations: 34 })
    expect(prepared.result.sheets[0].quoteData.purchasedPackageParts).toEqual(expect.arrayContaining([
      expect.objectContaining({ description: 'Color Box', perPartCostUsd: .12, included: 1 }),
    ]))
    expect(prepared.result.sheets[0].quoteData.moq5000Usd).toBe(2.84)

    const output = createDisneyCustomerQuoteWorkbook(
      prepared.result,
      readFileSync('public/templates/disney-customer-quote-template.bin'),
    )
    const parsed = parseXlsxWorkbook(asArrayBuffer(output))
    const tier = parsed.sheets[0]
    expect(tier.rows[8][2]).toBe(1000142435)
    expect(tier.rows[18][1]).toBe('1000142435-01')
    expect(tier.rows[18][2]).toBe(8900)
    expect(Number(tier.rows[18][12])).toBe(1)
    expect(Number(tier.rows[18][13])).toBe(1)
    expect(tier.rows[18][17]).toBe(39)
    expect(tier.rows[178][1]).toBe('Whole Item')
    expect(tier.rows[235][5]).toBe(3.08)
    expect(tier.rows[236][5]).toBe(2.84)
    expect(tier.rows[237][5]).toBe(2.64)
    const customerWorkbookText = parsed.sheets
      .flatMap((sheet) => sheet.rows)
      .flat()
      .map((value) => String(value ?? ''))
      .join('\n')
    expect(customerWorkbookText).not.toMatch(/测试费用|吊柜费|报价（MOQ|杂项|HK 40 柜/)
  })

  it('drives the Dickie customer template from complete P4-only fields', () => {
    const prepared = prepareP4CustomerConversion(
      p4Workbook(P4_ARTIFACT_TEMPLATE_VERSION, true, 'Dickie'),
      'IQ-P4-DICKIE-001.xlsx',
      'dicky',
    )
    expect(prepared.customerId).toBe('dicky')
    expect(prepared.result.p4QuoteData?.productRows[0]).toMatchObject({
      itemTextEn: expect.stringContaining('Stitch Cable Buggy'),
      price40hHkd: 25.3,
    })
    expect(prepared.result.p4QuoteData?.moldRows[0]).toMatchObject({
      moldNo: 'M01',
      partsEn: 'Car Bottom',
      moldCostHkd: 49000,
    })

    const output = createDickyCustomerQuoteWorkbook(
      prepared.result,
      readFileSync('public/templates/dicky-customer-quote-template.bin'),
    )
    const worksheets = unzipSync(output)
    const worksheetXml = Object.entries(worksheets)
      .filter(([path]) => /^xl\/worksheets\/sheet\d+\.xml$/.test(path))
      .map(([, bytes]) => strFromU8(bytes))
      .join('\n')
    expect(worksheetXml).toContain('Stitch Cable Buggy')
    expect(worksheetXml).toContain('Car Bottom')
    expect(worksheetXml).toContain('<v>49000</v>')
    expect(worksheetXml).toContain('<f>SUM(J48:J85)</f>')
  }, 30_000)

  it('blocks a BuzzBee color-box cost before consumption when either customer tier is missing', () => {
    expect(() => prepareP4CustomerConversion(
      p4Workbook(P4_ARTIFACT_TEMPLATE_VERSION, false),
      'buzzbee-missing-color-box-tiers.xlsx',
      'buzzbee',
    )).toThrow('彩盒必须完整填写两档报客价、FSC 与 MOQ')
  })
})
