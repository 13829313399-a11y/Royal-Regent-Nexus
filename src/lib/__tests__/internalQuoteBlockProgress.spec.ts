import { describe, expect, it } from 'vitest'

import { getInternalQuoteFormBlocks } from '@/lib/internalQuoteBlockProgress'
import { normalizeInternalQuotePayload } from '@/lib/internalQuoteSectionPayload'

function statuses(code: Parameters<typeof normalizeInternalQuotePayload>[0], value: Record<string, unknown>) {
  const payload = normalizeInternalQuotePayload(code, value)
  return Object.fromEntries(getInternalQuoteFormBlocks(code, payload).map((item) => [item.id, item.status]))
}

describe('internal quote form block progress', () => {
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
      product_size_cm: { length: 12, width: 8, height: 4 },
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
})
