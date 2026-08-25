import { describe, expect, it } from 'vitest'

import { getInternalQuoteFormBlocks } from '@/lib/internalQuoteBlockProgress'
import { normalizeInternalQuotePayload } from '@/lib/internalQuoteSectionPayload'

function statuses(code: Parameters<typeof normalizeInternalQuotePayload>[0], value: Record<string, unknown>) {
  const payload = normalizeInternalQuotePayload(code, value)
  return Object.fromEntries(getInternalQuoteFormBlocks(code, payload).map((item) => [item.id, item.status]))
}

describe('internal quote form block progress', () => {
  it('uses the same 部分 suffix for every department block navigation title', () => {
    const codes = ['engineering', 'electronic', 'molding', 'painting', 'slush', 'sewing', 'hair', 'assembly', 'sales'] as const
    for (const code of codes) {
      const payload = normalizeInternalQuotePayload(code, {})
      expect(getInternalQuoteFormBlocks(code, payload).every((item) => item.title.endsWith('部分'))).toBe(true)
    }
  })

  it('treats blank optional engineering blocks as ready and validates rows once started', () => {
    expect(statuses('engineering', {})).toMatchObject({
      hardware: 'optional',
      auxiliary: 'optional',
      molds: 'optional',
      'mold-allocation': 'optional',
    })

    expect(statuses('engineering', {
      materials: [{ category: 'hardware', item: '螺丝', quantity: 2, unit_price_rmb: 0 }],
    }).hardware).toBe('partial')

    expect(statuses('engineering', {
      materials: [{ category: 'hardware', item: '螺丝', quantity: 2, unit_price_rmb: 0.35 }],
    }).hardware).toBe('complete')

    expect(statuses('engineering', {
      materials: [{ category: 'hardware', item: '螺丝', quantity: 2, unit_price_rmb: 0.35, loss_rate: 0 }],
    }).hardware).toBe('partial')

    expect(statuses('engineering', {
      materials: [{ category: 'auxiliary', item: '胶袋', quantity: 2, unit_price_hkd: 1.5 }],
    }).auxiliary).toBe('complete')

    expect(statuses('engineering', {
      mold_allocation_enabled: false,
      production_mold_costs: [{ item: '', cost_rmb: 1000 }],
      amortization_qty: 0,
    })['mold-allocation']).toBe('optional')
  })

  it('requires at least one complete molding route', () => {
    expect(statuses('molding', {})).toMatchObject({ injection: 'missing', blow: 'missing' })

    expect(statuses('molding', {
      injection_lines: [{
        item: '公仔身体', material: 'ABS', grade: '750SW', net_weight_g: 35,
        machine_code: '20A', sets: 1, target_output: 1200, quantity: 1,
      }],
    })).toMatchObject({ injection: 'complete', blow: 'optional' })
  })

  it('marks sales packing and freight complete when carton data is usable', () => {
    const result = statuses('sales', {
      color_box_size_in: { length: 13, width: 9, height: 5 },
      cartons: [{ item: '主纸箱', length_in: 14, width_in: 9.25, height_in: 23.875, qty_per_carton: 2 }],
    })

    expect(result).toMatchObject({
      'testing-fee': 'optional',
      'packaging-materials': 'optional',
      cartons: 'complete',
      freight: 'complete',
    })
  })

  it('requires the capacity value for every custom freight capacity type', () => {
    const payload = normalizeInternalQuotePayload('sales', {
      color_box_size_in: { length: 13, width: 9, height: 5 },
      cartons: [{ item: '主纸箱', length_in: 14, width_in: 9.25, height_in: 23.875, qty_per_carton: 2 }],
    })
    const withoutCustomCapacity = getInternalQuoteFormBlocks('sales', payload, ['8 吨车容量'])
    expect(withoutCustomCapacity.find(({ id }) => id === 'freight')?.status).toBe('partial')

    const withCustomCapacity = normalizeInternalQuotePayload('sales', {
      ...payload,
      freight_calc: { ...payload.freight_calc, '8 吨车容量': 1200 },
    })
    const completed = getInternalQuoteFormBlocks('sales', withCustomCapacity, ['8 吨车容量'])
    expect(completed.find(({ id }) => id === 'freight')?.status).toBe('complete')
  })

  it('accepts HKD as the entered packaging-material unit price', () => {
    expect(statuses('sales', {
      packaging_materials: [{
        item: '彩盒',
        specification: '四彩',
        category: 'color_box_inner_card',
        quantity: 2,
        unit_price_hkd: 4,
      }],
    })['packaging-materials']).toBe('complete')

    expect(statuses('sales', {
      packaging_materials: [{
        item: '彩盒', specification: '四彩', category: 'color_box_inner_card',
        quantity: 2, unit_price_hkd: 4, loss_rate: 0,
      }],
    })['packaging-materials']).toBe('partial')
  })

  it('tracks the optional business testing fee once either USD total or MOQ is entered', () => {
    expect(statuses('sales', {})['testing-fee']).toBe('optional')
    expect(statuses('sales', { testing_fee_total_usd: 1250 })['testing-fee']).toBe('partial')
    expect(statuses('sales', { testing_fee_total_usd: 1250, testing_fee_moqs: [5000, 0] })['testing-fee']).toBe('partial')
    expect(statuses('sales', { testing_fee_total_usd: 1250, testing_fee_moqs: [5000, 10000] })['testing-fee']).toBe('complete')
    expect(statuses('sales', { testing_fee_total_usd: 1250, testing_fee_moq: 5000 })['testing-fee']).toBe('complete')
    expect(statuses('sales', { testing_fee_enabled: false, testing_fee_total_usd: 1250, testing_fee_moqs: [0] })['testing-fee']).toBe('complete')
  })

  it('accepts customer pickup as a complete freight choice', () => {
    const result = statuses('sales', { freight_calc: { enabled: false } })
    expect(result.freight).toBe('complete')
    expect(result.cartons).toBe('partial')
  })

  it('does not mark nested electronic rows complete until every child is priced', () => {
    expect(statuses('electronic', {
      components: [{ item: '主板', quantity: 1, children: [{ item: 'IC', quantity: 2 }] }],
    }).components).toBe('partial')

    expect(statuses('electronic', {
      components: [{ item: '主板', quantity: 1, children: [{ item: 'IC', quantity: 2, unit_price_rmb: 1.25 }] }],
    }).components).toBe('complete')
  })

  it('tracks electronic, painting and sewing quick quotes with their dedicated required fields', () => {
    expect(statuses('electronic', { quote_mode: 'quick', quick_quotes: [{ item: '', unit_price_rmb: 10, tax_rate_percent: 13 }] }).components).toBe('partial')
    expect(statuses('electronic', { quote_mode: 'quick', quick_quotes: [{ item: '主控板', unit_price_rmb: 10, tax_rate_percent: 101 }] }).components).toBe('partial')
    expect(statuses('electronic', { quote_mode: 'quick', quick_quotes: [{ item: '主控板', unit_price_rmb: 10, tax_rate_percent: 13 }] }).components).toBe('complete')

    expect(statuses('painting', { quote_mode: 'quick', quick_quote: {} }).painting).toBe('missing')
    expect(statuses('painting', { quote_mode: 'quick', quick_quote: { spray_labor_hkd: 2, paint_hkd: 3 } }).painting).toBe('complete')

    expect(statuses('sewing', { quote_mode: 'quick', quick_quotes: [{ doll_name: '公仔 A', unit_price_hkd: 0 }] }).sewing).toBe('partial')
    expect(statuses('sewing', { quote_mode: 'quick', quick_quotes: [{ doll_name: '公仔 A', unit_price_hkd: 4.25 }] }).sewing).toBe('complete')
  })

  it('requires every started standalone hair row to include its full quotation evidence', () => {
    expect(statuses('hair', {})).toEqual({ hair: 'missing' })
    expect(statuses('hair', {
      lines: [{ name: '公仔头发', craft: '植发', weight_g: 18.5, unit_price_hkd: 2.35 }],
    })).toEqual({ hair: 'partial' })
    expect(statuses('hair', {
      lines: [{ name: '公仔头发', craft: '植发', weight_g: 18.5, unit_price_hkd: 2.35, unit: 'PCS' }],
    })).toEqual({ hair: 'complete' })
  })

  it('tracks assembly summary, assembly work and packaging work independently', () => {
    expect(statuses('assembly', {})).toEqual({
      'assembly-summary': 'complete',
      'assembly-work': 'missing',
      'packaging-work': 'missing',
    })

    expect(statuses('assembly', {
      labor_base_hkd: 260,
      standard_work_hours: 11,
      groups: [
        { name: '组装成品', category: 'assembly', production_qty: 100, teams: 1, processes: [{ name: '锁螺丝', persons: 2 }] },
        { name: '包装成品', category: 'packaging', production_qty: 100, teams: 1, processes: [{ name: '装箱', persons: 2 }] },
      ],
    })).toEqual({
      'assembly-summary': 'complete',
      'assembly-work': 'complete',
      'packaging-work': 'complete',
    })

    expect(statuses('assembly', {
      groups: [
        { name: '组装成品', category: 'assembly', production_qty: 100, teams: 1, total_persons: 6, processes: [] },
        { name: '包装成品', category: 'packaging', production_qty: 100, teams: 1, total_persons: 4, processes: [] },
      ],
    })).toEqual({
      'assembly-summary': 'complete',
      'assembly-work': 'complete',
      'packaging-work': 'complete',
    })

    expect(statuses('assembly', {
      groups: [{ name: '组装成品', category: 'assembly', production_qty: 100, teams: 1, processes: [] }],
    })['assembly-work']).toBe('partial')
  })
})
