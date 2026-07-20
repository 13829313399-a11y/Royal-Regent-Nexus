import { describe, expect, it } from 'vitest'
import { isReactive, reactive } from 'vue'
import { calculateCartonCuft, calculateCartonPriceHkd, calculateCartonUnitCostHkd, calculateElectronicSummary, calculateEngineeringMoldAllocation, calculateEngineeringMoldPriceHkd, calculateFlatCardPriceHkd, calculatePackagingMaterialAmountHkd, calculatePackagingMaterialUnitHkd, calculatePaintingOperationTotals, calculatePaintingRowAmount, calculateSalesFreightOptions, calculateSewingBasePriceRmb, calculateSewingGroupTotalRmb, calculateSewingRowTotalRmb, calculateSewingTotalHkd, calculateSewingTotalRmb, calculateSlushRowAmount, calculateSlushTotalHkd, calculateSlushTotalRmb, cloneInternalQuotePayload, defaultSalesFreightCalculation, normalizeInternalQuotePayload, sewingGroupHasLaborLine, type ElectronicPayload, type EngineeringPayload, type PaintingPayload, type SewingPayload, type SlushPayload } from '@/lib/internalQuoteSectionPayload'

describe('internal quote section payload normalization', () => {
  it('omits retired sales cost fields for new forms while preserving historical payloads', () => {
    const fresh = normalizeInternalQuotePayload('sales', {})
    for (const key of ['additional_tax_hkd', 'indonesia_freight_hkd', 'tax_categories', 'scenarios']) {
      expect(fresh).not.toHaveProperty(key)
    }
    expect(fresh).toHaveProperty('customer_quote_fields')
    expect(fresh).toMatchObject({
      paper_price_factor: 2.75,
      packaging_materials: [],
      product_size_cm: { length: 0, width: 0, height: 0 },
      color_box_size_cm: { length: 0, width: 0, height: 0 },
      cartons: [],
      freight_calc: { enabled: true, cap_10t: 1166, cap_5t: 750, cap_40: 1980, cap_20: 883, hk40: 8000, yt5t: 11000 },
    })
    expect(fresh).not.toHaveProperty('flat_card_price_factor')
    expect(normalizeInternalQuotePayload('sales', { paper_price_factor: 2.8, flat_card_price_factor: 2.3 })).toMatchObject({
      paper_price_factor: 2.8,
      flat_card_price_factor: 2.3,
    })

    expect(normalizeInternalQuotePayload('sales', {
      additional_tax_hkd: 3,
      indonesia_freight_hkd: 4,
      tax_categories: [{ code: 'legacy', amount_hkd: 5, rate: '.13' }],
      scenarios: [{ name: '旧场景', capacity_cuft: 1980, carton_cuft: 2, qty_per_carton: 6 }],
    })).toMatchObject({
      additional_tax_hkd: 3,
      indonesia_freight_hkd: 4,
      tax_categories: [{ code: 'legacy', amount_hkd: 5, rate: .13 }],
      scenarios: [{ name: '旧场景', capacity_cuft: 1980 }],
    })
  })

  it('previews the accepted carton, flat-card, CUFT and per-piece formulas', () => {
    const packagingMaterial = { quantity: 2, unit_price_rmb: 3.4 }
    expect(calculatePackagingMaterialUnitHkd(packagingMaterial, .85)).toBeCloseTo(4)
    expect(calculatePackagingMaterialAmountHkd(packagingMaterial, .85)).toBeCloseTo(8)
    const carton = {
      item: '主纸箱',
      length_in: 10,
      width_in: 5,
      height_in: 4,
      qty_per_carton: 10,
      flat_cards: [{ name: '主平卡', length_in: 8, width_in: 4, quantity: 2 }],
    }
    expect(calculateCartonCuft(carton)).toBeCloseTo(0.1157407)
    expect(calculateCartonPriceHkd(carton, 2.75)).toBeCloseTo(0.935)
    expect(calculateFlatCardPriceHkd(carton.flat_cards[0], 2.75)).toBeCloseTo(0.495)
    expect(calculateFlatCardPriceHkd(carton.flat_cards[0], 1.5)).toBeCloseTo(0.27)
    expect(calculateCartonUnitCostHkd(carton, 2.75)).toBeCloseTo(0.143)
    expect(calculateCartonUnitCostHkd(carton, 2.75, 1.5)).toBeCloseTo(0.1205)

    const freightOptions = calculateSalesFreightOptions(defaultSalesFreightCalculation, {
      length_in: 14,
      width_in: 9.25,
      height_in: 23.875,
      qty_per_carton: 2,
    })
    expect(freightOptions).toHaveLength(8)
    const hk40 = freightOptions.find((option) => option.key === 'hk40')!
    expect(hk40.capacityCuft).toBe(1980)
    expect(hk40.totalCartons).toBe(Math.round(1980 / calculateCartonCuft({ length_in: 14, width_in: 9.25, height_in: 23.875 })))
    expect(hk40.perPieceHkd).toBeCloseTo(8000 / hk40.totalCartons / 2)
    expect(calculateSalesFreightOptions(defaultSalesFreightCalculation).every((option) => option.totalCartons === 0 && option.perPieceHkd === 0)).toBe(true)
    expect(calculateSalesFreightOptions({ ...defaultSalesFreightCalculation, enabled: false }, carton)).toEqual([])
    expect(normalizeInternalQuotePayload('sales', { freight_calc: { enabled: false, cap_40: 1980.6 } })).toMatchObject({
      freight_calc: { enabled: false, cap_40: 1981 },
    })
  })

  it('clones deeply reactive Vue sales forms into plain save payloads', () => {
    const form = reactive({
      scenarios: [{ name: '盐田', capacity_cuft: 1980, carton_cuft: 2, qty_per_carton: 6 }],
      customer_quote_fields: {
        buzzbee: {
          color_box_tiers: [{ quote_price_hkd: 6.7, fsc_price_hkd: 6.9, moq: 'MOQ3000' }],
        },
      },
    })

    expect(() => cloneInternalQuotePayload('sales', form)).not.toThrow()
    const cloned = cloneInternalQuotePayload('sales', form)
    expect(isReactive(cloned)).toBe(false)
    expect(isReactive((cloned.customer_quote_fields as Record<string, unknown>).buzzbee)).toBe(false)
    expect(cloned).toMatchObject({
      scenarios: [{ name: '盐田', capacity_cuft: 1980 }],
      customer_quote_fields: { buzzbee: { color_box_tiers: [{ quote_price_hkd: 6.7 }] } },
    })
  })

  it('normalizes every authoritative section contract without generic cost rows', () => {
    const engineering = normalizeInternalQuotePayload('engineering', { materials: [{ item: '螺丝', category: 'hardware', purpose: '尿兜', spec: '2.6*8PB', qty: '2', unit: 'pcs', unit_price_rmb: '3', material: '铁', surface_treatment: '镀镍', supplier: '港正', contact: '张/电话', tax_pct: '13', note: '样板' }], molds: [] })
    expect(engineering).toMatchObject({ materials: [{ item: '螺丝', category: 'hardware', purpose: '尿兜', specification: '2.6*8PB', quantity: 2, unit: 'pcs', unit_price_rmb: 3, material: '铁', surface_treatment: '镀镍', supplier: '港正', contact: '张/电话', tax_rate_percent: 13, remark: '样板', auxiliary_category: '其他外购' }] })
    expect(engineering).not.toHaveProperty('cartons')
    expect(normalizeInternalQuotePayload('electronic', { components: [{ item: 'IC', quantity: 2, unit_price_hkd: 1.5, children: [{ item: '脚位', quantity: 1, unit_price_hkd: .2 }] }] })).toMatchObject({ components: [{ item: 'IC', children: [{ item: '脚位' }] }], profit_rate_percent: 10 })
    expect(normalizeInternalQuotePayload('molding', { injection_lines: [{ material: 'ABS', grade: '750SW', machine_code: '20A' }] })).toMatchObject({ injection_lines: [{ material: 'ABS', grade: '750SW', loss_rate_percent: 3, machine_code: '20A' }] })
    expect(normalizeInternalQuotePayload('molding', {
      injection_loss_rate_percent: '4',
      injection_lines: [{ name: '主体模', mold_no: 'M-01', material: 'ABS', material_grade: '750SW', color: '黑色', weight_g: '100', machine: '80T', machine_model: '5A', cavity: '2', sets: '1', target: '5000', cycle_sec: '24', note: '客签色' }],
      blow_lines: [{ name: '吹气瓶', capacity: '12000', material: 'ABS', grade: '750SW', weight_g: '45', blow_labor: '.2', flash: '.1', profit_x: '1.05', cavity_note: '1出2', mold_price_note: '5000' }],
    })).toMatchObject({
      injection_loss_rate_percent: 4,
      injection_lines: [{ item: '主体模', mold_no: 'M-01', grade: '750SW', loss_rate_percent: 4, machine_name: '80T', machine_code: '5A', cavity: '2', target_output: 5000, cycle_time_seconds: 24, remark: '客签色' }],
      blow_lines: [{ item: '吹气瓶', daily_capacity: '12000', estimated_weight_g: 45, labor_hkd: .2, burr_hkd: .1, profit_multiplier: 1.05, output_count: '1出2', mold_price_rmb: 5000 }],
    })
    expect(normalizeInternalQuotePayload('painting', { rows: [{ item: '头部', position: '正面', image: '头部.png', note: '对色板', operations: { clamp: { quantity: 2, unit_price_hkd: 3 } } }] })).toMatchObject({ rows: [{ name: '头部', position: '正面', image_reference: '头部.png', remark: '对色板', operations: { clamp: { quantity: 2, unit_price_hkd: 3 }, wipe: { quantity: 0, unit_price_hkd: 0 }, pp_water: { quantity: 0, unit_price_hkd: 0 } } }] })
    expect(normalizeInternalQuotePayload('slush', { lines: [{ product_no: 'RC-01', name: '手臂', material: 'PVC', net_weight_g: '35', daily_output: '8000', usage: '2', unit_price_hkd: '4.5', note: '透明', source_row: '8' }] })).toEqual({ lines: [{ product_code: 'RC-01', item: '手臂', material: 'PVC', weight_g: 35, daily_output_24h: 8000, quantity: 2, unit_price_hkd: 4.5, remark: '透明', source_row: 8 }] })
    expect(normalizeInternalQuotePayload('sewing', { groups: [{ name: '衣服', category: '车衣', items: [{ fabric: '绒布', part: '身体', craft: '电绣', pieces: '4', qty: '0.25', mat_price: '12', markup: '1.1', note: '红色', supplier: 'A', source_row: '8' }] }] })).toEqual({ groups: [{ name: '衣服', category: 'clothes', labor_rmb: 0, materials: [{ item: '绒布', part: '身体', craft: '电绣', pieces: 4, usage: 0.25, unit_price_rmb: 12, markup: 1.1, remark: '红色', supplier: 'A', source_row: 8 }] }] })
    expect(normalizeInternalQuotePayload('assembly', { groups: [{ name: '包装', category: 'packaging', processes: [{ name: '入袋', persons: 2, teams: 1, production_qty: 100 }] }] })).toMatchObject({ labor_base_hkd: 260, groups: [{ category: 'packaging', processes: [{ production_qty: 100 }] }] })
    expect(normalizeInternalQuotePayload('assembly', { labor_base_hkd: 285, groups: [] })).toMatchObject({ labor_base_hkd: 285 })
    expect(normalizeInternalQuotePayload('sales', {
      packaging_materials: [{ item: '彩盒', specification: '四彩印刷', category: 'color_box_inner_card', quantity: '2', unit_price_rmb: '3.4', tax_rate_percent: '10', remark: 'FSC' }],
      freight_calc: { cap_40: '2000', hk40: '8200' },
      scenarios: [{ name: '盐田', capacity_cuft: 1980, carton_cuft: 2, qty_per_carton: 6 }],
      customer_quote_fields: { buzzbee: { color_box_tiers: [{ quote_price_hkd: '6.70', fsc_price_hkd: '6.90', moq: 'MOQ3000' }] } },
    })).toMatchObject({
      packaging_materials: [{ item: '彩盒', category: 'color_box_inner_card', quantity: 2, unit_price_rmb: 3.4, tax_rate_percent: 10, remark: 'FSC' }],
      freight_calc: { cap_40: 2000, hk40: 8200, cap_10t: 1166, yt5t: 11000 },
      scenarios: [{ name: '盐田', freight_share: .48, lift_share: .52, markup: 1.2, settlement: .98 }],
      customer_quote_fields: { buzzbee: { color_box_tiers: [{ quote_price_hkd: 6.7, fsc_price_hkd: 6.9, moq: 'MOQ3000' }] } },
    })
  })

  it('previews painting row, process and section totals across all eight operations', () => {
    const payload = normalizeInternalQuotePayload('painting', {
      rows: [
        { name: '外壳', position: '正面', operations: { clamp: { quantity: 2, unit_price_hkd: .12 }, pp_water: { quantity: 3, unit_price_hkd: .08 } } },
        { name: '外壳', position: '背面', operations: { pp_water: { quantity: 1, unit_price_hkd: .08 } } },
      ],
    }) as unknown as PaintingPayload

    expect(calculatePaintingRowAmount(payload.rows[0])).toBeCloseTo(.48)
    expect(calculatePaintingOperationTotals(payload)).toMatchObject({ clamp: .24, pp_water: .32 })
    expect(payload.rows.reduce((total, row) => total + calculatePaintingRowAmount(row), 0)).toBeCloseTo(.56)
  })

  it('previews slush line, HKD total and RMB total from the frozen rate', () => {
    const payload = normalizeInternalQuotePayload('slush', {
      lines: [
        { product_code: 'RC-01', item: '手臂', quantity: 2, unit_price_hkd: 3.6 },
        { product_code: 'RC-02', item: '头部', quantity: 1.5, unit_price_hkd: 2 },
      ],
    }) as unknown as SlushPayload

    expect(calculateSlushRowAmount(payload.lines[0])).toBeCloseTo(7.2)
    expect(calculateSlushTotalHkd(payload)).toBeCloseTo(10.2)
    expect(calculateSlushTotalRmb(payload, .85)).toBeCloseTo(8.67)
  })

  it('previews sewing base price, markup total, labor de-duplication and frozen-rate HKD', () => {
    const payload = normalizeInternalQuotePayload('sewing', {
      groups: [
        {
          name: '外套', category: 'clothes', labor_rmb: 12,
          materials: [{ item: '绒布', part: '身体', craft: '电绣', pieces: 4, usage: .25, unit_price_rmb: 12, markup: 1.1 }],
        },
        {
          name: '发套', category: 'hair', labor_rmb: 100,
          materials: [{ item: '车缝人工', part: '', pieces: 0, usage: 1, unit_price_rmb: 5, markup: 0 }],
        },
      ],
    }) as unknown as SewingPayload

    expect(calculateSewingBasePriceRmb(payload.groups[0].materials[0])).toBeCloseTo(3)
    expect(calculateSewingRowTotalRmb(payload.groups[0].materials[0])).toBeCloseTo(3.3)
    expect(calculateSewingGroupTotalRmb(payload.groups[0])).toBeCloseTo(15.3)
    expect(sewingGroupHasLaborLine(payload.groups[1])).toBe(true)
    expect(calculateSewingGroupTotalRmb(payload.groups[1])).toBeCloseTo(5)
    expect(calculateSewingTotalRmb(payload)).toBeCloseTo(20.3)
    expect(calculateSewingTotalHkd(payload, .85)).toBeCloseTo(23.88235294)
  })

  it('previews the electronic RMB, tax-credit and frozen-rate formulas', () => {
    const electronic = normalizeInternalQuotePayload('electronic', {
      pricing_currency: 'RMB',
      components: [{
        item: 'IC', specification: 'A1', quantity: 2, unit_price_rmb: .45, tax_rate_percent: 13, remark: '主控',
        children: [{ item: '', specification: 'A2', quantity: 18, unit_price_rmb: .002, tax_rate_percent: 13 }],
      }],
      bonding_rmb: 0,
      smt_rmb: .496,
      labor_rmb: .6925,
      testing_rmb: .14,
      packaging_rmb: .023,
      profit_rate_percent: 10,
    }) as unknown as ElectronicPayload

    expect(electronic.components[0]).toMatchObject({ specification: 'A1', unit_price_rmb: .45, tax_rate_percent: 13, remark: '主控' })
    const summary = calculateElectronicSummary(electronic, .85)
    expect(summary.componentCostRmb).toBeCloseTo(.936)
    expect(summary.preTaxCostRmb).toBeCloseTo(2.2875)
    expect(summary.deductibleInputTaxRmb).toBeCloseTo(.936 / 1.13 * .13)
    expect(summary.taxDifferenceRmb).toBeCloseTo(2.51625 * .13 - .936 / 1.13 * .13)
    expect(summary.quoteRmb).toBeCloseTo(2.7576242)
    expect(summary.quoteHkd).toBeCloseTo(3.2442638)
  })

  it('normalizes the complete mold sheet and production allocation contract', () => {
    const engineering = normalizeInternalQuotePayload('engineering', {
      materials: [],
      molds: [{
        name: '主体模', mold_no: 'M-01', mold_type: 'CI 3040', structure: '两板模', material: 'S50C', color: '红', cavity: '2',
        sets: '2', weight_g: '120', cycle_sec: '35', mold_size: '300×400', image_reference: 'M-01.png', price_rmb: '5000', note: '客户确认',
        machine_code: '20A', target_output: '5000', source_row: '8',
      }],
      production_mold_costs: [{ name: '模具费用', price_rmb: '1550' }],
      mold_fx_rmb_usd: '7.75', amortization_qty: '100', customer_mold_subsidy_usd: '10',
      prototype_total_usd: '500', prototype_amortization_qty: '50000', testing_total_usd: '100', testing_amortization_qty: '2000',
    }) as unknown as EngineeringPayload

    expect(engineering.molds[0]).toMatchObject({
      item: '主体模', mold_no: 'M-01', mold_base_type: 'CI 3040', structure: '两板模', material: 'S50C', color: '红', cavity: '2',
      quantity: 2, net_weight_g: 120, cycle_time_seconds: 35, mold_size: '300×400', image_reference: 'M-01.png', cost_rmb: 5000,
      remark: '客户确认', machine_code: '20A', target_output: 5000, source_row: 8,
    })
    expect(engineering.production_mold_costs).toEqual([{ item: '模具费用', cost_rmb: 1550 }])
    expect(calculateEngineeringMoldPriceHkd(engineering.molds[0], .85)).toBeCloseTo(5882.3529)
    expect(calculateEngineeringMoldAllocation(engineering)).toMatchObject({
      productionTotalRmb: 1550,
      productionTotalUsd: 200,
      moldShareRmb: 15.5,
      moldShareUsd: 1.9,
      prototypeShareRmb: .0775,
      prototypeShareUsd: .01,
      testingShareRmb: .3875,
      testingShareUsd: .05,
      totalShareRmb: 15.965,
      totalShareUsd: 1.96,
    })

    const legacy = normalizeInternalQuotePayload('engineering', {
      molds: [{ item: '旧模具', quantity: 2, cost_rmb: 1000 }],
    }) as unknown as EngineeringPayload
    expect(legacy.production_mold_costs).toEqual([
      { item: '模具费用', cost_rmb: 1000 },
      { item: '超声模费用', cost_rmb: 0 },
      { item: '喷油模具', cost_rmb: 0 },
    ])
    expect(legacy).toMatchObject({ mold_fx_rmb_usd: 7.75, amortization_qty: 20000, prototype_amortization_qty: 50000, testing_amortization_qty: 2000 })
  })

  it('preserves the Disney P4-only field contract in its owning sections', () => {
    expect(normalizeInternalQuotePayload('engineering', {
      materials: [{ item: '螺丝', category: 'hardware', quantity: '1', unit_price_rmb: '2', disney_description: 'Screw', disney_section: 'product', disney_unit_price_usd: '.02', disney_included: '6' }],
      molds: [{ item: '车面模', quantity: 1, cost_rmb: 1000, disney_mold_no: 'M02', disney_parts: '车面', disney_material: 'ABS', disney_cavities: '1', disney_parts_per_shot: '1', disney_tool_cost_usd: '8900' }],
      cartons: [{ item: '外箱', length_in: 12, width_in: 10, height_in: 4, qty_per_carton: 6, disney_unit_price_usd: '.062', flat_cards: [] }],
    })).toMatchObject({
      materials: [{ disney_description: 'Screw', disney_section: 'product', disney_unit_price_usd: .02, disney_included: 6 }],
      molds: [{ disney_mold_no: 'M02', disney_cavities: 1, disney_parts_per_shot: 1, disney_tool_cost_usd: 8900 }],
      cartons: [{ disney_unit_price_usd: .062 }],
    })
    expect(normalizeInternalQuotePayload('molding', {
      injection_lines: [{ item: '车面', material: 'ABS', grade: '750SW', disney_mold_no: 'M02', disney_resin_cost_usd_kg: '6.32', disney_cycle_time_seconds: '39', disney_labor_rate_usd_hr: '10.77' }],
    })).toMatchObject({ injection_lines: [{ disney_mold_no: 'M02', disney_resin_cost_usd_kg: 6.32, disney_cycle_time_seconds: 39, disney_labor_rate_usd_hr: 10.77 }] })
    expect(normalizeInternalQuotePayload('painting', {
      rows: [], disney_decorations: [{ application_type: 'Whole Item', rate_per_op_usd: '.0171', operations: '34' }],
    })).toEqual({ rows: [], disney_decorations: [{ application_type: 'Whole Item', rate_per_op_usd: .0171, operations: 34 }] })
    expect(normalizeInternalQuotePayload('sales', {
      customer_quote_fields: { disney: { item_number: '1000142435', quote_date: '2026-06-03', revision: '0', minimum_order_qty: '3000', moq_prices_usd: { qty_3000: '3.42', qty_5000: '3.17', qty_10000: '2.93' }, transportation_usd: '.027', model_cost_usd: '6200', setup_charge_usd: '1500' } },
    })).toMatchObject({ customer_quote_fields: { disney: { item_number: '1000142435', minimum_order_qty: 3000, moq_prices_usd: { qty_3000: 3.42, qty_5000: 3.17, qty_10000: 2.93 }, model_cost_usd: 6200 } } })
  })

  it('preserves the Dickie product, English term, material and mold field contract', () => {
    expect(normalizeInternalQuotePayload('engineering', {
      materials: [],
      cartons: [],
      molds: [{
        item: '车底模', quantity: 1, cost_rmb: 44100,
        dickie_project_name_en: '20 307 3001\nStitch Cable Buggy', dickie_mold_no: 'M01', dickie_parts_en: 'Car Bottom', dickie_resin: 'C-ABS', dickie_mold_size: '30*35*30', dickie_mold_material: 'NAK80', dickie_cavities: '16', dickie_parts_per_shot: '8', dickie_mold_cost_hkd: '49000', dickie_remark_en: 'Common Mold',
      }],
    })).toMatchObject({ molds: [{ dickie_mold_no: 'M01', dickie_parts_en: 'Car Bottom', dickie_cavities: 16, dickie_parts_per_shot: 8, dickie_mold_cost_hkd: 49000, dickie_remark_en: 'Common Mold' }] })

    expect(normalizeInternalQuotePayload('sales', {
      customer_quote_fields: { dickie: {
        client_name: 'Simba Dickie toys', quote_date: '2026-05-15', attention: 'Sam', revision: '', from_name: 'Ben / Dickie', project_name_en: 'Disney Cable Car', first_shot_time: '45 Working Days', finish_time: '75 Working Days',
        product_rows: [{ line_no: '1', item_text_en: 'Stitch Cable Buggy', units_per_carton: '0/12', carton_cbm: '.047', color_box_size_cm: '24*11*12cm', carton_size_cm: '49.8*35.2*27cm', production_moq: '5K-10K', price_40h_hkd: '25.3', price_20h_hkd: '25.7', price_lcl_hkd: '25.8' }],
        remark_lines: [{ line_no: '1', text_en: 'Estimate based on the picture.' }],
        material_prices_hkd: [{ material: 'PP', price_hkd_lb: '5.8' }],
      } },
    })).toMatchObject({ customer_quote_fields: { dickie: {
      client_name: 'Simba Dickie toys',
      product_rows: [{ line_no: 1, carton_cbm: .047, price_40h_hkd: 25.3, price_20h_hkd: 25.7, price_lcl_hkd: 25.8 }],
      remark_lines: [{ line_no: 1, text_en: 'Estimate based on the picture.' }],
      material_prices_hkd: [{ material: 'PP', price_hkd_lb: 5.8 }],
    } } })
  })

  it('preserves the Caixing Tool Plan, customer mold mapping and template groups', () => {
    expect(normalizeInternalQuotePayload('engineering', {
      molds: [{ item: '剑柄模', caixing_tool_plan_ref: '1', caixing_mold_cost_hkd: '50588.23', caixing_customer_mold_cost_hkd: '53623.53' }],
    })).toMatchObject({ molds: [{ caixing_tool_plan_ref: '1', caixing_mold_cost_hkd: 50588.23, caixing_customer_mold_cost_hkd: 53623.53 }] })
    expect(normalizeInternalQuotePayload('molding', {
      caixing_tool_plan_rows: [{ ref_no: '1', process_type: 'IN', tooling_cost_hkd: '53623.53', description: '剑柄上盖', sku_no: '68963', cavities: '2', up: '2', net_weight_g: '120', material_code: '1', material: 'ABS', material_cost_hkd: '1.98', machine_size: '14', cycle_time_seconds: '26', process_cost_hkd: '.229' }],
    })).toMatchObject({ caixing_tool_plan_rows: [{ ref_no: '1', process_type: 'IN', cavities: 2, up: 2, cycle_time_seconds: 26, process_cost_hkd: .229 }] })
    expect(normalizeInternalQuotePayload('sales', {
      customer_quote_fields: { caixing: { product_type: 'plush', item_number: '40636', item_name: 'Bijou Big Beats', quote_date: '2026-06-02', carton_length_in: '10.5', carton_width_in: '8.375', carton_height_in: '9.25', carton_cuft: '.47', carton_cbm: '.013', pcs_per_carton: '4', carton_price_hkd: '2.426', cost_rows: [{ group: 'fabric', category: '车衣', description: '衣服/裙子', base_cost_hkd: '3.88', customer_cost_hkd: '3.9592' }] } },
    })).toMatchObject({ customer_quote_fields: { caixing: { product_type: 'plush', item_number: '40636', carton_length_in: 10.5, cost_rows: [{ group: 'fabric', customer_cost_hkd: 3.9592 }] } } })
  })
})
