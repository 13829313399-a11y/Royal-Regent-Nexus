import { describe, expect, it } from 'vitest'
import { isReactive, reactive } from 'vue'
import { calculateAssemblyCategoryLaborHkd, calculateAssemblyGroupLaborHkd, calculateAssemblyGroupPeople, calculateCartonCuft, calculateCartonPriceHkd, calculateCartonUnitCostHkd, calculateElectronicSummary, calculateEngineeringMaterialAmountHkd, calculateEngineeringMaterialUnitRmb, calculateEngineeringMoldAllocation, calculateEngineeringMoldPriceHkd, calculateFlatCardPriceHkd, calculateHairRowAmountHkd, calculateHairTotalHkd, calculatePackagingMaterialAmountHkd, calculatePackagingMaterialUnitHkd, calculatePackagingMaterialUnitRmb, calculatePaintingOperationTotals, calculatePaintingQuickPaintTaxHkd, calculatePaintingTotalHkd, calculatePaintingRowAmount, calculateSalesFreightOptions, calculateSalesTestingFeeUnitUsd, calculateSewingBasePriceRmb, calculateSewingGroupTotalRmb, calculateSewingQuickTotalHkd, calculateSewingRowTotalRmb, calculateSewingTotalHkd, calculateSewingTotalRmb, calculateSlushRowAmount, calculateSlushTotalHkd, calculateSlushTotalRmb, cloneInternalQuotePayload, createDefaultSalesMarkupTiers, defaultSalesFreightCalculation, dimensionValueFromInches, dimensionValueToInches, normalizeInternalQuotePayload, salesFreightReferenceRoutesFromSnapshot, salesMarkupTierForQuantity, sewingGroupHasLaborLine, splitEngineeringMoldPartNames, type AssemblyPayload, type ElectronicPayload, type EngineeringPayload, type HairPayload, type PaintingPayload, type SalesPayload, type SewingPayload, type SlushPayload } from '@/lib/internalQuoteSectionPayload'

describe('internal quote section payload normalization', () => {
  it('omits retired sales cost fields for new forms while preserving historical payloads', () => {
    const fresh = normalizeInternalQuotePayload('sales', {})
    for (const key of ['additional_tax_hkd', 'indonesia_freight_hkd', 'tax_categories', 'scenarios']) {
      expect(fresh).not.toHaveProperty(key)
    }
    expect(fresh).toHaveProperty('customer_quote_fields')
    expect(fresh).toMatchObject({
      customer_quote_fields: {
        three_sixty: {
          ms_brand: '',
          prepared_by: '郑大能',
          quote_date: '',
          revision: '0',
          first_etd: '',
          freight_route_key: '',
        },
      },
    })
    expect(fresh).toMatchObject({
      paper_price_factor: 2.75,
      testing_fee_total_usd: 0,
      testing_fee_moqs: [0],
      packaging_materials: [],
      product_size_in: { length: 0, width: 0, height: 0 },
      color_box_size_unit: 'inch',
      color_box_size_in: { length: 0, width: 0, height: 0 },
      cartons: [{
        item: '主纸箱',
        size_unit: 'inch',
        length_in: 0,
        width_in: 0,
        height_in: 0,
        qty_per_carton: 1,
        flat_cards: [],
      }],
      freight_calc: { enabled: true, freight_enabled: true, lifting_enabled: true, cap_10t: 1166, cap_5t: 750, cap_40: 1980, cap_20: 883 },
    })
    expect(fresh.freight_calc).not.toHaveProperty('hk40')
    expect(fresh.freight_calc).not.toHaveProperty('yt5t')
    expect(fresh).not.toHaveProperty('flat_card_price_factor')
    expect(fresh).not.toHaveProperty('product_size_cm')
    expect(fresh).not.toHaveProperty('color_box_size_cm')
    expect(fresh).not.toHaveProperty('shipping')
    expect(normalizeInternalQuotePayload('sales', { cartons: [] }).cartons).toEqual([{
      item: '主纸箱',
      size_unit: 'inch',
      length_in: 0,
      width_in: 0,
      height_in: 0,
      qty_per_carton: 1,
      flat_cards: [],
    }])
    expect(normalizeInternalQuotePayload('sales', { paper_price_factor: 2.8, flat_card_price_factor: 2.3 })).toMatchObject({
      paper_price_factor: 2.8,
      flat_card_price_factor: 2.3,
    })
    expect(normalizeInternalQuotePayload('sales', {
      testing_fee_total_usd: '1250',
      testing_fee_moq: '5000',
    })).toMatchObject({
      testing_fee_total_usd: 1250,
      testing_fee_moqs: [5000],
    })
    expect(normalizeInternalQuotePayload('sales', {
      testing_fee_total_usd: '1250',
      testing_fee_moqs: ['3000', '5000', 10000],
    })).toMatchObject({
      testing_fee_total_usd: 1250,
      testing_fee_moqs: [3000, 5000, 10000],
    })
    expect(calculateSalesTestingFeeUnitUsd(1250, 5000)).toBe(.25)
    expect(calculateSalesTestingFeeUnitUsd(1250, 0)).toBe(0)
    expect(normalizeInternalQuotePayload('sales', {
      shipping: {
        markup_x: '1.15',
        markup_tiers: [{ moq: '3000', markup_x: '1.25' }, { moq: '5000', markup_x: '1.20' }, { moq: '10000', markup_x: '1.15' }],
        selected_markup_moq: '5000',
        misc_ratio: '.035',
        divisor: '.98',
        freight_pct: '48',
        lifting_pct: '52',
      },
    })).toMatchObject({
      shipping: {
        markup_x: 1.15,
        markup_tiers: [{ moq: 3000, markup_x: 1.25 }, { moq: 5000, markup_x: 1.2 }, { moq: 10000, markup_x: 1.15 }],
        selected_markup_moq: 5000,
        misc_ratio: .035,
        divisor: .98,
        freight_pct: 48,
        lifting_pct: 52,
      },
    })
    expect(normalizeInternalQuotePayload('sales', {
      product_size_cm: { length: '5.25', width: '8.75', height: '3' },
      color_box_size_cm: { length: '6', width: '9', height: '3.5' },
    })).toMatchObject({
      product_size_in: { length: 5.25, width: 8.75, height: 3 },
      color_box_size_in: { length: 6, width: 9, height: 3.5 },
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

  it('creates the three default MOQ tiers and selects the highest reached tier', () => {
    const tiers = createDefaultSalesMarkupTiers(1.2)
    tiers[0]!.markup_x = 1.3
    tiers[1]!.markup_x = 1.25
    tiers[2]!.markup_x = 1.15
    expect(tiers.map((tier) => tier.moq)).toEqual([3000, 5000, 10000])
    expect(salesMarkupTierForQuantity(tiers, 2000)).toEqual({ moq: 3000, markup_x: 1.3 })
    expect(salesMarkupTierForQuantity(tiers, 7000)).toEqual({ moq: 5000, markup_x: 1.25 })
    expect(salesMarkupTierForQuantity(tiers, 10000)).toEqual({ moq: 10000, markup_x: 1.15 })
    expect(salesMarkupTierForQuantity(tiers, 50000)).toEqual({ moq: 10000, markup_x: 1.15 })
  })

  it('preserves cm/inch display units while keeping calculation dimensions in canonical inches', () => {
    const normalized = normalizeInternalQuotePayload('sales', {
      color_box_size_unit: 'cm',
      color_box_size_in: { length: 10, width: 5, height: 4 },
      cartons: [{ item: '主纸箱', size_unit: 'cm', length_in: 20, width_in: 10, height_in: 8, qty_per_carton: 2, flat_cards: [] }],
    })
    expect(normalized).toMatchObject({
      color_box_size_unit: 'cm',
      color_box_size_in: { length: 10, width: 5, height: 4 },
      cartons: [{ size_unit: 'cm', length_in: 20, width_in: 10, height_in: 8 }],
    })
    expect(dimensionValueFromInches(10, 'cm')).toBe(25.4)
    expect(dimensionValueToInches(25.4, 'cm')).toBe(10)
    expect(dimensionValueFromInches(10, 'inch')).toBe(10)
    expect(dimensionValueToInches(10, 'inch')).toBe(10)
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
    expect(calculateFlatCardPriceHkd(carton.flat_cards[0], 2.75)).toBeCloseTo(0.176)
    expect(calculateFlatCardPriceHkd(carton.flat_cards[0], 1.5)).toBeCloseTo(0.096)
    expect(calculateFlatCardPriceHkd({ length_in: 10, width_in: 5, quantity: 1 }, 2.75)).toBeCloseTo(0.1375)
    expect(calculateCartonUnitCostHkd(carton, 2.75)).toBeCloseTo(0.1111)
    expect(calculateCartonUnitCostHkd(carton, 2.75, 1.5)).toBeCloseTo(0.1031)

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
    const baselineOptions = calculateSalesFreightOptions(
      normalizeInternalQuotePayload('sales', {}).freight_calc,
      { length_in: 14, width_in: 9.25, height_in: 23.875, qty_per_carton: 2 },
      salesFreightReferenceRoutesFromSnapshot({
        routes: [{ route_key: 'sz40', route_name: '深圳 40 柜', capacity_key: 'cap_40', freight_hkd: '6500', lifting_hkd: '1100' }],
      }),
    )
    expect(baselineOptions).toHaveLength(1)
    expect(baselineOptions[0]).toMatchObject({
      key: 'sz40',
      label: '深圳 40 柜',
      freightCostHkd: 6500,
      liftingCostHkd: 1100,
    })
    expect(baselineOptions[0].freightPerPieceHkd).toBeCloseTo(6500 / baselineOptions[0].totalCartons / 2)
    expect(baselineOptions[0].liftingPerPieceHkd).toBeCloseTo(1100 / baselineOptions[0].totalCartons / 2)
    expect(baselineOptions[0].perPieceHkd).toBeCloseTo(7600 / baselineOptions[0].totalCartons / 2)
    const customCapacityFreight = normalizeInternalQuotePayload('sales', {
      freight_calc: { '8 吨车容量': 1200 },
    }).freight_calc
    const customCapacityOptions = calculateSalesFreightOptions(
      customCapacityFreight,
      { length_in: 12, width_in: 12, height_in: 12, qty_per_carton: 10 },
      salesFreightReferenceRoutesFromSnapshot({
        routes: [{ route_key: 'hk8t', route_name: 'HK 8 吨车', capacity_key: '8 吨车容量', freight_hkd: '6000', lifting_hkd: '800' }],
      }),
    )
    expect(customCapacityFreight['8 吨车容量']).toBe(1200)
    expect(customCapacityOptions).toHaveLength(1)
    expect(customCapacityOptions[0]).toMatchObject({ capacityKey: '8 吨车容量', capacityCuft: 1200, totalCartons: 1200 })
    expect(customCapacityOptions[0].perPieceHkd).toBeCloseTo(6800 / 1200 / 10)
    const freightOnlyOptions = calculateSalesFreightOptions(
      { ...defaultSalesFreightCalculation, freight_enabled: true, lifting_enabled: false },
      { length_in: 14, width_in: 9.25, height_in: 23.875, qty_per_carton: 2 },
      salesFreightReferenceRoutesFromSnapshot({
        routes: [{ route_key: 'sz40', route_name: '深圳 40 柜', capacity_key: 'cap_40', freight_hkd: '6500', lifting_hkd: '1100' }],
      }),
    )
    expect(freightOnlyOptions[0].freightCostHkd).toBe(6500)
    expect(freightOnlyOptions[0].liftingCostHkd).toBe(0)
    expect(freightOnlyOptions[0].liftingPerPieceHkd).toBe(0)
    expect(freightOnlyOptions[0].perPieceHkd).toBeCloseTo(6500 / freightOnlyOptions[0].totalCartons / 2)
    expect(salesFreightReferenceRoutesFromSnapshot({ cost_hkd: { hk_container_40: '8200' } })[0].freightCostHkd).toBe(8200)
    expect(calculateSalesFreightOptions(defaultSalesFreightCalculation).every((option) => option.totalCartons === 0 && option.perPieceHkd === 0)).toBe(true)
    expect(calculateSalesFreightOptions({ ...defaultSalesFreightCalculation, enabled: false }, carton)).toEqual([])
    expect(normalizeInternalQuotePayload('sales', { freight_calc: { enabled: false, cap_40: 1980.6 } })).toMatchObject({
      freight_calc: { enabled: false, freight_enabled: false, lifting_enabled: false, cap_40: 1981 },
    })
  })

  it('uses the selected RMB or HKD source price for packaging and auxiliary materials', () => {
    const packagingPayload = normalizeInternalQuotePayload('sales', {
      packaging_materials: [{
        item: '吸塑罩',
        category: 'blister',
        quantity: 2,
        unit_price_hkd: 4,
        unit_price_source_currency: 'HKD',
      }],
    }) as unknown as SalesPayload
    const packagingHkd = packagingPayload.packaging_materials[0]
    expect(packagingHkd).toMatchObject({
      unit_price_rmb: 0,
      unit_price_hkd: 4,
      unit_price_source_currency: 'HKD',
    })
    expect(calculatePackagingMaterialUnitRmb(packagingHkd, .85)).toBeCloseTo(3.4)
    expect(calculatePackagingMaterialUnitHkd(packagingHkd, .85)).toBe(4)
    expect(calculatePackagingMaterialAmountHkd(packagingHkd, .85)).toBe(8)

    const engineeringPayload = normalizeInternalQuotePayload('engineering', {
      materials: [{
        item: '胶袋',
        category: 'auxiliary',
        quantity: 3,
        unit_price_hkd: 1.5,
      }],
    }) as unknown as EngineeringPayload
    const auxiliaryHkd = engineeringPayload.materials[0]
    expect(auxiliaryHkd).toMatchObject({
      unit_price_source_currency: 'HKD',
      unit_price_hkd: 1.5,
    })
    expect(calculateEngineeringMaterialUnitRmb(auxiliaryHkd, .85)).toBeCloseTo(1.275)
    expect(calculateEngineeringMaterialAmountHkd(auxiliaryHkd, .85)).toBeCloseTo(4.5)

    const historicalPayload = normalizeInternalQuotePayload('sales', {
      packaging_materials: [{ item: '彩盒', category: 'color_box_inner_card', quantity: 2, unit_price_rmb: 3.4 }],
    }) as unknown as SalesPayload
    const historicalRmb = historicalPayload.packaging_materials[0]
    expect(historicalRmb.unit_price_source_currency).toBe('RMB')
    expect(calculatePackagingMaterialUnitHkd(historicalRmb, .85)).toBeCloseTo(4)
  })

  it('clones deeply reactive Vue sales forms into plain save payloads', () => {
    const form = reactive({
      scenarios: [{ name: '盐田', capacity_cuft: 1980, carton_cuft: 2, qty_per_carton: 6 }],
      shipping: { markup_x: 1.15 },
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
      shipping: { markup_x: 1.15 },
      customer_quote_fields: { buzzbee: { color_box_tiers: [{ quote_price_hkd: 6.7 }] } },
    })
  })

  it('normalizes every authoritative section contract without generic cost rows', () => {
    const engineering = normalizeInternalQuotePayload('engineering', { materials: [{ item: '螺丝', category: 'hardware', purpose: '尿兜', spec: '2.6*8PB', qty: '2', unit: 'pcs', unit_price_rmb: '3', material: '铁', surface_treatment: '镀镍', supplier: '港正', contact: '张/电话', tax_pct: '13', note: '样板' }], molds: [] })
    expect(engineering).toMatchObject({ materials: [{ item: '螺丝', category: 'hardware', purpose: '尿兜', specification: '2.6*8PB', quantity: 2, unit: 'pcs', unit_price_rmb: 3, material: '铁', surface_treatment: '镀镍', supplier: '港正', contact: '张/电话', tax_rate_percent: 13, remark: '样板', auxiliary_category: '五金' }] })
    expect(normalizeInternalQuotePayload('engineering', { materials: [{ item: '旧五金', category: 'hardware', auxiliary_category: '其他外购', tax_rate_percent: 0 }] })).toMatchObject({ materials: [{ auxiliary_category: '五金', tax_rate_percent: 13 }] })
    expect(engineering).not.toHaveProperty('cartons')
    expect(normalizeInternalQuotePayload('electronic', { components: [{ item: 'IC', quantity: 2, unit_price_hkd: 1.5, children: [{ item: '脚位', quantity: 1, unit_price_hkd: .2 }] }] })).toMatchObject({ components: [{ item: 'IC', children: [{ item: '脚位' }] }], profit_rate_percent: 10 })
    expect(normalizeInternalQuotePayload('molding', { injection_lines: [{ engineering_source_key: 'mold-no:M01#1', engineering_synced_fields: ['mold_no', 'material'], material: 'ABS', grade: '750SW', machine_code: '20A' }] })).toMatchObject({ injection_lines: [{ engineering_source_key: 'mold-no:M01#1', engineering_synced_fields: ['mold_no', 'material'], material: 'ABS', grade: '750SW', loss_rate_percent: 3, machine_code: '20A' }] })
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
    expect(normalizeInternalQuotePayload('sewing', { groups: [{ name: '衣服', category: '车衣', items: [{ fabric: '绒布', part: '身体', craft: '电绣', pieces: '4', qty: '0.25', mat_price: '12', markup: '1.1', note: '红色', supplier: 'A', source_row: '8' }] }] })).toEqual({ quote_mode: 'detail', quick_quotes: [], groups: [{ name: '衣服', category: 'clothes', labor_rmb: 0, materials: [{ item: '绒布', part: '身体', craft: '电绣', pieces: 4, usage: 0.25, unit_price_rmb: 12, markup: 1.1, remark: '红色', supplier: 'A', source_row: 8 }] }] })
    expect(normalizeInternalQuotePayload('hair', { lines: [{ item: '公仔头发', process: '植发', weight_g: '18.5', unit_price_hkd: '2.35', unit: 'PCS', note: '棕色' }] })).toEqual({ lines: [{ name: '公仔头发', craft: '植发', weight_g: 18.5, unit_price_hkd: 2.35, unit: 'PCS', remark: '棕色' }] })
    expect(normalizeInternalQuotePayload('assembly', { groups: [{ name: '包装', category: 'packaging', processes: [{ name: '入袋', persons: 2, teams: 1, production_qty: 100, note: '检查封口' }] }] })).toMatchObject({ labor_base_hkd: 260, standard_work_hours: 11, groups: [{ category: 'packaging', production_qty: 100, teams: 1, processes: [{ name: '入袋', persons: 2, remark: '检查封口' }] }] })
    expect(normalizeInternalQuotePayload('assembly', { labor_base_hkd: 285, standard_work_hours: 10.5, groups: [] })).toMatchObject({ labor_base_hkd: 285, standard_work_hours: 10.5 })
    expect(normalizeInternalQuotePayload('sales', {
      packaging_materials: [{ item: '彩盒', specification: '四彩印刷', category: 'color_box_inner_card', quantity: '2', unit_price_rmb: '3.4', tax_rate_percent: '10', remark: 'FSC' }],
      freight_calc: { cap_40: '2000', hk40: '8200' },
      scenarios: [{ name: '盐田', capacity_cuft: 1980, carton_cuft: 2, qty_per_carton: 6 }],
      customer_quote_fields: { buzzbee: { color_box_tiers: [{ quote_price_hkd: '6.70', fsc_price_hkd: '6.90', moq: 'MOQ3000' }] } },
    })).toMatchObject({
      packaging_materials: [{ item: '彩盒', category: 'color_box_inner_card', quantity: 2, unit_price_rmb: 3.4, tax_rate_percent: 10, remark: 'FSC' }],
      freight_calc: { cap_40: 2000, hk40: 8200, cap_10t: 1166 },
      scenarios: [{ name: '盐田', freight_share: .48, lift_share: .52, markup: 1.2, settlement: .98 }],
      customer_quote_fields: { buzzbee: { color_box_tiers: [{ quote_price_hkd: 6.7, fsc_price_hkd: 6.9, moq: 'MOQ3000' }] } },
    })
  })

  it('calculates assembly and packaging labor per product group', () => {
    const payload = normalizeInternalQuotePayload('assembly', {
      labor_base_hkd: 260,
      standard_work_hours: 11,
      groups: [
        { name: '成品组装', category: 'assembly', production_qty: 100, teams: 2, processes: [{ name: '锁螺丝', persons: 3 }, { name: '装配', persons: 2 }] },
        { name: '包装', category: 'packaging', production_qty: 200, teams: 1, processes: [{ name: '装箱', persons: 4 }] },
      ],
    }) as AssemblyPayload

    expect(calculateAssemblyGroupPeople(payload.groups[0])).toBe(5)
    expect(calculateAssemblyGroupLaborHkd(payload.groups[0], payload.labor_base_hkd)).toBe(26)
    expect(calculateAssemblyCategoryLaborHkd(payload, 'assembly')).toBe(26)
    expect(calculateAssemblyCategoryLaborHkd(payload, 'packaging')).toBe(5.2)
  })

  it('copies product-group capacity into legacy assembly process fields when saving', () => {
    const payload = normalizeInternalQuotePayload('assembly', {
      labor_base_hkd: 260,
      standard_work_hours: 11,
      groups: [{
        name: '火螺装工',
        category: 'assembly',
        production_qty: '3000',
        teams: '1',
        processes: [{ name: '装配', persons: '42', production_qty: '0', teams: '9' }],
      }],
    }) as AssemblyPayload

    expect(payload.groups[0]).toMatchObject({
      production_qty: 3000,
      teams: 1,
      processes: [{ name: '装配', persons: 42, production_qty: 3000, teams: 1 }],
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

  it('normalizes and previews painting and sewing quick quotes without counting preserved details', () => {
    const painting = normalizeInternalQuotePayload('painting', {
      quote_mode: 'quick',
      quick_quote: { spray_labor_hkd: '2', paint_hkd: '3', paint_tax_rate_percent: 99 },
      rows: [{ name: '保留明细', operations: { spray: { quantity: 10, unit_price_hkd: 10 } } }],
    }) as unknown as PaintingPayload
    expect(painting.quick_quote.paint_tax_rate_percent).toBe(13)
    expect(calculatePaintingQuickPaintTaxHkd(painting)).toBeCloseTo(.39)
    expect(calculatePaintingTotalHkd(painting)).toBeCloseTo(5.39)

    const sewing = normalizeInternalQuotePayload('sewing', {
      quote_mode: 'quick',
      quick_quotes: [{ name: '公仔 A', price_hkd: '4.25' }, { doll_name: '公仔 B', unit_price_hkd: '5.75' }],
      groups: [{ name: '保留明细', materials: [{ item: '布', usage: 10, unit_price_rmb: 10 }] }],
    }) as unknown as SewingPayload
    expect(sewing.quick_quotes).toEqual([{ doll_name: '公仔 A', unit_price_hkd: 4.25 }, { doll_name: '公仔 B', unit_price_hkd: 5.75 }])
    expect(calculateSewingQuickTotalHkd(sewing)).toBe(10)
    expect(calculateSewingTotalHkd(sewing, .85)).toBe(10)
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

  it('previews standalone hair unit prices and the department HKD total', () => {
    const payload = normalizeInternalQuotePayload('hair', {
      lines: [
        { name: '公仔头发', craft: '植发', weight_g: 18.5, unit_price_hkd: 2.35, unit: 'PCS' },
        { name: '尾巴毛', craft: '车发', weight_g: 3, unit_price_hkd: .65, unit: 'PCS' },
      ],
    }) as HairPayload

    expect(calculateHairRowAmountHkd(payload.lines[0])).toBeCloseTo(2.35)
    expect(calculateHairTotalHkd(payload)).toBeCloseTo(3)
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

  it('normalizes electronic quick rows and excludes preserved detail rows from the active quote', () => {
    const electronic = normalizeInternalQuotePayload('electronic', {
      quote_mode: 'quick',
      quick_quotes: [
        { name: '主控板', price_rmb: '10', tax_rate_percent: '13', note: '含税' },
        { item: '喇叭', unit_price_rmb: '5', tax_rate_percent: '0', remark: '不含税' },
      ],
      components: [{ item: '保留明细', quantity: 1, unit_price_rmb: 999, tax_rate_percent: 13 }],
      profit_rate_percent: 10,
    }) as unknown as ElectronicPayload

    expect(electronic).toMatchObject({
      quote_mode: 'quick',
      quick_quotes: [
        { item: '主控板', unit_price_rmb: 10, tax_rate_percent: 13, remark: '含税' },
        { item: '喇叭', unit_price_rmb: 5, tax_rate_percent: 0, remark: '不含税' },
      ],
      pricing_currency: 'RMB',
    })
    const summary = calculateElectronicSummary(electronic, .85)
    expect(summary.componentCostRmb).toBe(15)
    expect(summary.deductibleInputTaxRmb).toBeCloseTo(10 / 1.13 * .13)
    expect(summary.quoteRmb).toBeCloseTo(17.5940133)
    expect(summary.quoteHkd).toBeCloseTo(20.6988392)
  })

  it('normalizes the complete mold sheet and production allocation contract', () => {
    const engineering = normalizeInternalQuotePayload('engineering', {
      materials: [],
      mold_allocation_enabled: true,
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
      chinese_name: '', mold_base_material: '', process: '', material_type: '', mold_specification: '',
      quantity: 2, net_weight_g: 120, cycle_time_seconds: 35, mold_size: '300×400', image_reference: 'M-01.png', cost_rmb: 5000,
      remark: '客户确认', machine_code: '20A', target_output: 5000, parts: [{ name: '主体模', output_count: 1, quantity: 1 }], source_row: 8,
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
    const allocationDisabled = normalizeInternalQuotePayload('engineering', {
      ...engineering,
      mold_allocation_enabled: false,
    }) as unknown as EngineeringPayload
    expect(calculateEngineeringMoldAllocation(allocationDisabled)).toMatchObject({
      productionTotalRmb: 0,
      moldShareUsd: 0,
      prototypeShareUsd: 0,
      testingShareUsd: 0,
      totalShareRmb: 0,
      totalShareUsd: 0,
    })

    const legacy = normalizeInternalQuotePayload('engineering', {
      molds: [{ item: '旧模具', quantity: 2, cost_rmb: 1000 }],
    }) as unknown as EngineeringPayload
    expect(legacy.production_mold_costs).toEqual([
      { item: '模具费用', cost_rmb: 1000 },
      { item: '超声模费用', cost_rmb: 0 },
      { item: '喷油模具', cost_rmb: 0 },
    ])
    expect(legacy).toMatchObject({ mold_allocation_enabled: true, mold_fx_rmb_usd: 7.75, amortization_qty: 20000, prototype_amortization_qty: 50000, testing_amortization_qty: 2000 })
  })

  it('splits engineering mold child parts from left-right and slash names while preserving saved child data', () => {
    expect(splitEngineeringMoldPartNames('左右前枪身（橙色）')).toEqual([
      '左前枪身（橙色）',
      '右前枪身（橙色）',
    ])
    expect(splitEngineeringMoldPartNames('泵杆/击锤/扣机/配件(7件)')).toEqual([
      '泵杆',
      '击锤',
      '扣机',
      '配件(7件)',
    ])
    expect(splitEngineeringMoldPartNames('电池箱／底座／压盖／配件')).toEqual([
      '电池箱',
      '底座',
      '压盖',
      '配件',
    ])

    const engineering = normalizeInternalQuotePayload('engineering', {
      molds: [{
        item: '左右前枪身（橙色）',
        parts: [{ name: '手工命名', color: '橙色', unit_net_weight_g: '12.5', output_count: '2', quantity: '1' }],
      }],
    }) as unknown as EngineeringPayload
    expect(engineering.molds[0].parts).toEqual([{
      name: '手工命名',
      color: '橙色',
      process: '',
      process_unit_price_hkd: 0,
      unit_net_weight_g: 12.5,
      output_count: 2,
      quantity: 1,
    }])
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
    })).toEqual({ quote_mode: 'detail', quick_quote: { spray_labor_hkd: 0, paint_hkd: 0, paint_tax_rate_percent: 13 }, rows: [], disney_decorations: [{ application_type: 'Whole Item', rate_per_op_usd: .0171, operations: 34 }] })
    expect(normalizeInternalQuotePayload('sales', {
      packaging_materials: [{
        item: '彩盒', specification: '四彩', category: 'color_box_inner_card', quantity: '1', unit_price_rmb: '3',
        disney_description: 'Color Box', disney_unit_price_usd: '.42', disney_included: '1',
      }],
      customer_quote_fields: { disney: { item_number: '1000142435', quote_date: '2026-06-03', revision: '0', minimum_order_qty: '3000', moq_prices_usd: { qty_3000: '3.42', qty_5000: '3.17', qty_10000: '2.93' }, transportation_usd: '.027', model_cost_usd: '6200', setup_charge_usd: '1500' } },
    })).toMatchObject({
      packaging_materials: [{ disney_description: 'Color Box', disney_unit_price_usd: .42, disney_included: 1 }],
      customer_quote_fields: { disney: { item_number: '1000142435', minimum_order_qty: 3000, moq_prices_usd: { qty_3000: 3.42, qty_5000: 3.17, qty_10000: 2.93 }, model_cost_usd: 6200 } },
    })
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
    })).toMatchObject({ customer_quote_fields: { caixing: { product_type: 'plush', item_number: '40636', item_name: 'Bijou Big Beats', quote_date: '2026-06-02' } } })
    expect((normalizeInternalQuotePayload('sales', {
      customer_quote_fields: { caixing: { carton_length_in: '10.5', cost_rows: [{ group: 'fabric' }] } },
    }) as Record<string, Record<string, Record<string, unknown>>>).customer_quote_fields.caixing).not.toHaveProperty('carton_length_in')
  })

  it('preserves only the non-duplicated 360 customer header and freight selection fields', () => {
    expect(normalizeInternalQuotePayload('sales', {
      customer_quote_fields: {
        three_sixty: {
          ms_brand: 'Cuddle Baby',
          prepared_by: '郑大能',
          quote_date: '2026-06-26',
          revision: 1,
          first_etd: '2026-08-01',
          freight_route_key: 'yt40',
          carton_length_in: 24.75,
        },
      },
    })).toMatchObject({
      customer_quote_fields: {
        three_sixty: {
          ms_brand: 'Cuddle Baby',
          prepared_by: '郑大能',
          quote_date: '2026-06-26',
          revision: '1',
          first_etd: '2026-08-01',
          freight_route_key: 'yt40',
        },
      },
    })
    expect((normalizeInternalQuotePayload('sales', {
      customer_quote_fields: { three_sixty: { carton_length_in: 24.75 } },
    }) as SalesPayload).customer_quote_fields.three_sixty).not.toHaveProperty('carton_length_in')
  })
})
