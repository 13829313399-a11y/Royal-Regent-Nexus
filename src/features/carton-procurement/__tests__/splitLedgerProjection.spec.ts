import { describe, expect, it } from 'vitest'
import type { CartonOrderResponse } from '@/api/cartonProcurement'
import type { SplitRecord } from '@/api/cartonOrderSplits'
import { projectSplitLedger } from '../splitLedgerProjection'

const paper = (id: string, quantity: string, received: string, unit = '张') => ({ id, packaging_type: id,
  paper_quality: 'A33', specification: '10*20', unit, required_quantity: quantity, received_quantity: received })
const order = (): CartonOrderResponse => ({ id: 'O1', factory_id: 'huadeng', order_no: 'CT1', customer_code: 'C1',
  item_no: 'ITEM1', contract_no: 'A', product_order_quantity: '1000',
  lines: [paper('outer', '1000', '600'), paper('inner', '2000', '1200')], split_records: [] } as unknown as CartonOrderResponse)
const targetLine = (id: string, targetId: string, pending: string, stock: string, arrived: string) => ({
  order_line_id: id, target_line_id: targetId, packaging_type: id, paper_quality: 'A33', specification: '10*20',
  unit: '张', pending_quantity: pending, received_quantity: arrived, pending_remaining: String(Number(pending) - Number(arrived)),
  stock: stock === '0' ? [] : [{ location_id: 'L1', expected_position_revision: 2, quantity: stock }],
})
const plan = (status: SplitRecord['status'] = 'ACTIVE'): SplitRecord => ({ id: 'P1', factory_id: 'huadeng', order_id: 'O1',
  order_no: 'CT1', customer_code: 'C1', item_no: 'ITEM1', status, revision: 1, reason: 'test', created_at: '', created_by_name: '',
  targets: [{ contract_no: 'B', customer_po: 'PO-B', product_quantity: '300', lines: [
    targetLine('outer', 'CH-OUT', '200', '100', '50'), targetLine('inner', 'CH-IN', '400', '200', '100'),
  ] }],
})

describe('split ledger read projection', () => {
  it('conserves every paper quantity and receipt plus product quantity across multiple destinations', () => {
    const source = order(), split = plan()
    split.targets.push({ contract_no: 'C', customer_po: 'PO-C', product_quantity: '100', lines: [
      targetLine('outer', 'C-OUT', '100', '0', '25'), targetLine('inner', 'C-IN', '200', '0', '50'),
    ] })
    source.split_records = [split]
    const before = JSON.stringify(source), result = projectSplitLedger(source)
    expect(result.valid).toBe(true)
    expect(result.parent.productQuantity).toBe('600')
    expect(result.parent.lines.map(line => [line.quantity, line.received, line.remaining])).toEqual([
      ['600', '425', '175'], ['1200', '850', '350'],
    ])
    expect(result.children[0]?.lines.map(line => [line.quantity, line.received, line.remaining])).toEqual([
      ['300', '150', '150'], ['600', '300', '300'],
    ])
    for (const original of result.original.lines) {
      const parent = result.parent.lines.find(line => line.orderLineId === original.orderLineId)!
      for (const key of ['quantity', 'received', 'remaining'] as const) {
        expect(Number(parent[key]) + result.children.reduce((sum, child) => sum + Number(child.lines.find(line => line.orderLineId === original.orderLineId)![key]), 0)).toBe(Number(original[key]))
      }
    }
    expect(result.children[0]?.key).toBe(projectSplitLedger(source).children[0]?.key)
    expect(result.children[0]?.key).not.toBe(result.children[1]?.key)
    expect(JSON.stringify(source)).toBe(before)
  })

  it('shows pending warehouse as preview without received amounts or parent deductions and omits cancelled plans', () => {
    const source = order()
    source.split_records = [plan('PENDING_WAREHOUSE'), { ...plan('CANCELLED'), id: 'cancelled' }]
    const result = projectSplitLedger(source)
    expect(result.valid).toBe(true)
    expect(result.parent).toEqual(result.original)
    expect(result.children).toHaveLength(1)
    expect(result.children[0]?.status).toBe('PENDING_WAREHOUSE')
    expect(result.children[0]?.lines.map(line => [line.quantity, line.received, line.remaining])).toEqual([
      ['300', '0', '300'], ['600', '0', '600'],
    ])
  })

  it('supports unreceived pending-only and fully received stock-only allocations', () => {
    for (const stockOnly of [false, true]) {
      const source = order(), split = plan()
      source.lines = [paper('outer', '1000', stockOnly ? '1000' : '0')] as CartonOrderResponse['lines']
      split.targets[0]!.lines = [targetLine('outer', 'CH', stockOnly ? '0' : '300', stockOnly ? '300' : '0', '0')]
      source.split_records = [split]
      const result = projectSplitLedger(source)
      expect(result.valid).toBe(true)
      expect(result.parent.lines[0]?.quantity).toBe('700')
      expect(result.children[0]?.lines[0]?.received).toBe(stockOnly ? '300' : '0')
      expect(result.parent.lines[0]?.received).toBe(stockOnly ? '700' : '0')
    }
  })

  it('keeps decimal arithmetic exact including quantities beyond safe JS integer precision and six-place products', () => {
    const source = order(), split = plan()
    source.product_order_quantity = '1.123456'
    source.lines = [paper('outer', '99999999999999.1234', '0.2001', '米')] as CartonOrderResponse['lines']
    split.targets[0]!.product_quantity = '0.100001'
    split.targets[0]!.lines = [{ ...targetLine('outer', 'CH', '0.1001', '0.1', '0.0001'), unit: '米' }]
    source.split_records = [split]
    const result = projectSplitLedger(source)
    expect(result.valid).toBe(true)
    expect(result.parent.productQuantity).toBe('1.023455')
    expect(result.parent.lines[0]).toMatchObject({ quantity: '99999999999998.9233', received: '0.1', remaining: '99999999999998.8233' })
    expect(result.children[0]?.lines[0]).toMatchObject({ quantity: '0.2001', received: '0.1001', remaining: '0.1' })
  })

  it.each(['factory_id', 'order_id', 'customer_code', 'item_no'] as const)('ignores unbound %s rather than inferring links', field => {
    const source = order()
    source.split_records = [{ ...plan(), [field]: 'FOREIGN' }]
    const result = projectSplitLedger(source)
    expect(result.valid).toBe(true)
    expect(result.children).toEqual([])
    expect(result.parent).toEqual(result.original)
  })

  it.each(['over_quantity', 'over_received', 'over_product', 'precision', 'fractional_count', 'negative', 'unknown_line', 'duplicate', 'wrong_unit'])(
    'fails closed for %s and does not partially subtract valid earlier targets', issue => {
      const source = order(), good = plan(), bad = plan()
      bad.id = 'P2'
      bad.targets[0]!.lines = [targetLine('outer', 'CH-BAD', '10', '0', '0')]
      bad.targets[0]!.product_quantity = '10'
      const line = bad.targets[0]!.lines[0]!
      if (issue === 'over_quantity') line.pending_quantity = '1000'
      if (issue === 'over_received') { line.pending_quantity = '600'; line.received_quantity = '600' }
      if (issue === 'over_product') bad.targets[0]!.product_quantity = '900'
      if (issue === 'precision') line.pending_quantity = '0.00001'
      if (issue === 'fractional_count') line.pending_quantity = '0.5'
      if (issue === 'negative') line.pending_quantity = '-1'
      if (issue === 'unknown_line') line.order_line_id = 'UNKNOWN'
      if (issue === 'duplicate') bad.id = good.id
      if (issue === 'wrong_unit') line.unit = '米'
      source.split_records = [good, bad]
      const result = projectSplitLedger(source)
      expect(result.valid).toBe(false)
      expect(result.errors[0]).toContain('拆单数量待核实')
      expect(result.children).toEqual([])
      expect(result.parent).toEqual(result.original)
    },
  )

  it('does not invent an unknown explicit product remainder', () => {
    const source = order(), split = plan()
    split.targets[0]!.product_quantity = null
    source.split_records = [split]
    expect(projectSplitLedger(source).parent.productQuantity).toBeNull()
    source.product_order_quantity = null
    expect(projectSplitLedger(source).original.productQuantity).toBeNull()
  })

  it('rejects pending previews that exceed capacity already allocated by active plans', () => {
    const source = order(), pending = plan('PENDING_WAREHOUSE')
    pending.id = 'PREVIEW'
    pending.targets[0]!.lines = [targetLine('outer', 'PREVIEW-OUT', '800', '0', '0')]
    source.split_records = [plan(), pending]
    const result = projectSplitLedger(source)
    expect(result.valid).toBe(false)
    expect(result.parent).toEqual(result.original)
    expect(result.children).toEqual([])
  })
})
