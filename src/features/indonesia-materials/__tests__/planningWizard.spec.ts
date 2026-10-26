import { describe, expect, it } from 'vitest'
import { checkedBucket, emptyDraftBucket, recordDraftId } from '../draftPersistence'
import { packingBalance } from '../packingBalance'
import { planningInfo } from '../planning'
import type { BoardOrder, MaterialRecord } from '@/api/indonesiaMaterials'

describe('wizard preservation and calculations', () => {
  it('reads old confirmation identities without migrating or discarding existing drafts', () => {
    const id = recordDraftId('shipment', 'confirm', 'shipment-a')
    const bucket = emptyDraftBucket()
    bucket.drafts[id] = { id, revision: 'old', writer: 'old-tab', savedAt: '2026-10-25', state: { confirming: { id: 'shipment-a', kind: 'shipment', version: 3 } } }
    expect(checkedBucket(bucket)).toEqual(bucket)
    bucket.drafts[id]!.state.confirming.id = 'different-shipment'
    expect(() => checkedBucket(bucket)).toThrow('身份不一致')
  })
  it('keeps confirmation revisions separate and refuses a mismatched version', () => {
    const id = recordDraftId('shipment', 'confirm', 'shipment-a', '4')
    const bucket = emptyDraftBucket()
    bucket.drafts[id] = { id, revision: 'new', writer: 'new-tab', savedAt: '2026-10-25', state: { confirming: { id: 'shipment-a', kind: 'shipment', version: 4 } } }
    expect(checkedBucket(bucket)).toEqual(bucket)
    bucket.drafts[id]!.state.confirming.version = 3
    expect(() => checkedBucket(bucket)).toThrow('身份不一致')
  })
  it('balances normal and spare quantities independently with eight-place exact arithmetic', () => {
    const line = { allocation_id: 'a', normal_quantity: '123456789012.12345678', spare_quantity: '0.00000001' }
    const form = { lines: [line], packages: [{ items: [{ ...line, normal_quantity: '123456789012' }] }, { items: [{ ...line, normal_quantity: '0.12345678', spare_quantity: '0' }] }] }
    expect(packingBalance(form)).toEqual([])
    form.packages[1]!.items[0]!.spare_quantity = '0.00000001'
    expect(packingBalance(form)).toEqual([{ id: 'a', message: '备品量多装 0.00000001' }])
    form.packages = []
    expect(packingBalance(form)[0]!.message).toBe('正常量还差 123456789012.12345678')
  })
  it('distinguishes missing values from existing defaults awaiting contract synchronization, including zero days', () => {
    const order = { id: 'o', customer: 'C', item_no: 'P', plan: { transport_days: 0 }, demands: [{ material_id: 'm', procurement_days: 0 }] } as BoardOrder
    const records = [
      { id: 'p', kind: 'product', version: 1, data: { customer: 'C', code: 'P', daily_capacity: '100', transport_days: 0 } },
      { id: 'm', kind: 'material', version: 1, data: { procurement_days: 0 } },
      { id: 'o', kind: 'order', version: 1, data: { product_snapshot: { data: { daily_capacity: '100.0' } } } },
    ] as MaterialRecord[]
    expect(planningInfo(order, records).label).toBe('计划齐全')
    records[0]!.data.daily_capacity = '200'
    expect(planningInfo(order, records).label).toBe('资料已更新，待同步')
    records[1]!.data.procurement_days = null
    expect(planningInfo(order, records).label).toContain('采购周期')
  })
})
