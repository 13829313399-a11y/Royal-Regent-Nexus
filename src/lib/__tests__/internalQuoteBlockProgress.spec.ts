import { describe, expect, it } from 'vitest'

import { getInternalQuoteFormBlocks } from '@/lib/internalQuoteBlockProgress'
import { normalizeInternalQuotePayload } from '@/lib/internalQuoteSectionPayload'

function statuses(code: Parameters<typeof normalizeInternalQuotePayload>[0], value: Record<string, unknown>) {
  const payload = normalizeInternalQuotePayload(code, value)
  return Object.fromEntries(getInternalQuoteFormBlocks(code, payload).map((item) => [item.id, item.status]))
}

describe('internal quote form block progress', () => {
  it('uses the same 部分 suffix for every department block navigation title', () => {
    const codes = ['engineering', 'electronic', 'molding', 'painting', 'slush', 'sewing', 'assembly', 'sales'] as const
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
      color_box_size_cm: { length: 13, width: 9, height: 5 },
      cartons: [{ item: '主纸箱', length_in: 14, width_in: 9.25, height_in: 23.875, qty_per_carton: 2 }],
    })

    expect(result).toMatchObject({
      'packaging-materials': 'optional',
      cartons: 'complete',
      freight: 'complete',
    })
  })

  it('accepts customer pickup as a complete freight choice', () => {
    const result = statuses('sales', { freight_calc: { enabled: false } })
    expect(result.freight).toBe('complete')
    expect(result.cartons).toBe('missing')
  })

  it('does not mark nested electronic rows complete until every child is priced', () => {
    expect(statuses('electronic', {
      components: [{ item: '主板', quantity: 1, children: [{ item: 'IC', quantity: 2 }] }],
    }).components).toBe('partial')

    expect(statuses('electronic', {
      components: [{ item: '主板', quantity: 1, children: [{ item: 'IC', quantity: 2, unit_price_rmb: 1.25 }] }],
    }).components).toBe('complete')
  })

  it('tracks painting and sewing quick quotes with their dedicated required fields', () => {
    expect(statuses('painting', { quote_mode: 'quick', quick_quote: {} }).painting).toBe('missing')
    expect(statuses('painting', { quote_mode: 'quick', quick_quote: { spray_labor_hkd: 2, paint_hkd: 3 } }).painting).toBe('complete')

    expect(statuses('sewing', { quote_mode: 'quick', quick_quotes: [{ doll_name: '公仔 A', unit_price_hkd: 0 }] }).sewing).toBe('partial')
    expect(statuses('sewing', { quote_mode: 'quick', quick_quotes: [{ doll_name: '公仔 A', unit_price_hkd: 4.25 }] }).sewing).toBe('complete')
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
  })
})
