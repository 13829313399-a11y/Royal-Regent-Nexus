import { describe, expect, it } from 'vitest'
import { normalizeInternalQuotePayload } from '@/lib/internalQuoteSectionPayload'

describe('internal quote section payload normalization', () => {
  it('normalizes every authoritative section contract without generic cost rows', () => {
    expect(normalizeInternalQuotePayload('engineering', { materials: [{ item: '螺丝', category: 'hardware', quantity: '2', unit_price_rmb: '3' }], molds: [], cartons: [] })).toMatchObject({ materials: [{ item: '螺丝', category: 'hardware', quantity: 2, unit_price_rmb: 3 }] })
    expect(normalizeInternalQuotePayload('electronic', { components: [{ item: 'IC', quantity: 2, unit_price_hkd: 1.5, children: [{ item: '脚位', quantity: 1, unit_price_hkd: .2 }] }] })).toMatchObject({ components: [{ item: 'IC', children: [{ item: '脚位' }] }], profit_rate_percent: 10 })
    expect(normalizeInternalQuotePayload('molding', { injection_lines: [{ material: 'ABS', grade: '750SW', machine_code: '20A' }] })).toMatchObject({ injection_lines: [{ material: 'ABS', grade: '750SW', loss_rate_percent: 3, machine_code: '20A' }] })
    expect(normalizeInternalQuotePayload('painting', { rows: [{ item: '头部', operations: { clamp: { quantity: 2, unit_price_hkd: 3 } } }] })).toMatchObject({ rows: [{ operations: { clamp: { quantity: 2, unit_price_hkd: 3 }, wipe: { quantity: 0, unit_price_hkd: 0 } } }] })
    expect(normalizeInternalQuotePayload('slush', { lines: [{ item: '手臂', quantity: '2', unit_price_hkd: '4.5' }] })).toEqual({ lines: [{ item: '手臂', quantity: 2, unit_price_hkd: 4.5 }] })
    expect(normalizeInternalQuotePayload('sewing', { groups: [{ name: '衣服', category: 'clothes', materials: [{ item: '布', usage: 2, unit_price_rmb: 3 }] }] })).toMatchObject({ groups: [{ category: 'clothes', materials: [{ markup: 1 }] }] })
    expect(normalizeInternalQuotePayload('assembly', { groups: [{ name: '包装', category: 'packaging', processes: [{ name: '入袋', persons: 2, teams: 1, production_qty: 100 }] }] })).toMatchObject({ labor_base_hkd: 310, groups: [{ category: 'packaging', processes: [{ production_qty: 100 }] }] })
    expect(normalizeInternalQuotePayload('sales', {
      scenarios: [{ name: '盐田', capacity_cuft: 1980, carton_cuft: 2, qty_per_carton: 6 }],
      customer_quote_fields: { buzzbee: { color_box_tiers: [{ quote_price_hkd: '6.70', fsc_price_hkd: '6.90', moq: 'MOQ3000' }] } },
    })).toMatchObject({
      scenarios: [{ name: '盐田', freight_share: .48, lift_share: .52, markup: 1.2, settlement: .98 }],
      customer_quote_fields: { buzzbee: { color_box_tiers: [{ quote_price_hkd: 6.7, fsc_price_hkd: 6.9, moq: 'MOQ3000' }] } },
    })
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
