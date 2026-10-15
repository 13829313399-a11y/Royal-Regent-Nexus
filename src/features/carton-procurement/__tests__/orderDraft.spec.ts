import { describe, expect, it } from 'vitest'
import {
  orderDraftKey, readOrderDraft, removeOrderDraft, writeOrderDraft,
  type OrderDraft, type OrderDraftContext,
} from '../orderDraft'

const context: OrderDraftContext = { userId: 'warehouse-a', employmentEpoch: 2, factoryId: 'huaxing' }
function draft(): OrderDraft {
  return {
    form: {
      customerPo: 'PO-00012', quantityBasis: 'CALCULATED', customerCode: '', supplierId: '',
      contractNo: 'SC-00012', itemNo: '00125', productName: '', orderQuantity: '',
      orderDate: '2026-10-14', customerDueDate: '', dueDate: '', note: '尚待核对',
      materials: [{ id: 'first', packagingType: '', paperQuality: '', specification: '30*20*15',
        unitsPerCarton: '', netWeight: '', grossWeight: 0, unit: '个', dimensionUnit: 'cm',
        unitPrice: 0, currency: 'CNY', priceSource: 'manual', note: '' }],
    },
    customerSearchText: '客户名称待确认',
    copiedOrderNo: 'CT-SOURCE', master: { id: 'CONFIG-1', revision: 3, code: '00125', factory_id: 'huaxing' },
    history: { item_no: '00125', latest_order_no: 'CT-SOURCE' }, schedule: null,
  }
}
function storage() {
  const values = new Map<string, string>()
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value) },
    removeItem: (key: string) => { values.delete(key) },
  }
}

describe('unfinished carton order storage', () => {
  it('restores a saved supplemental-order stage without treating the delivery as total demand', () => {
    const saved = storage(), pending = draft()
    pending.supplierDelivery = { factoryId: 'huaxing', shipmentId: 'SHIP', sourceLineId: 'SOURCE',
      deliveryNoteNo: 'DN', supplierId: '', contractNo: 'SC', itemNo: 'ITEM', customerPo: '', createdOrderNo: 'CT-SAVED',
      papers: [{ id: 'SOURCE', order_line_id: null, source_type: 'AD_HOC_REVIEW', order_no: '',
        contract_no: 'SC', customer_po: '', item_no: 'ITEM', customer_name: '', child_no: '',
        packaging_type: '普通箱', paper_quality: 'A33', specification: '10*20*30', unit: '个', quantity: '836' }] }
    writeOrderDraft(saved, context, pending)
    expect(readOrderDraft(saved, context)?.supplierDelivery).toEqual(pending.supplierDelivery)
    expect(readOrderDraft(saved, context)?.form.orderQuantity).toBe('')
    pending.supplierDelivery.factoryId = 'huakang-a'
    writeOrderDraft(saved, context, pending)
    expect(readOrderDraft(saved, context)).toBeNull()
  })
  it('restores incomplete fields, leading-zero identities, weights and source revision unchanged', () => {
    const saved = storage(), pending = draft()
    writeOrderDraft(saved, context, pending)
    expect(readOrderDraft(saved, context)).toEqual(pending)
  })

  it.each([
    { ...context, userId: 'warehouse-b' },
    { ...context, employmentEpoch: 3 },
    { ...context, factoryId: 'huakang-a' },
  ])('isolates an unfinished order from another account, employment or factory: %j', other => {
    const saved = storage()
    writeOrderDraft(saved, context, draft())
    expect(readOrderDraft(saved, other)).toBeNull()
    // Copying the stored bytes to another key cannot defeat the embedded scope check.
    saved.setItem(orderDraftKey(other), saved.getItem(orderDraftKey(context))!)
    expect(readOrderDraft(saved, other)).toBeNull()
    expect(readOrderDraft(saved, context)?.form.itemNo).toBe('00125')
  })

  it('refuses a packaging configuration from another factory without deleting the stored evidence', () => {
    const saved = storage(), pending = draft()
    pending.master!.factory_id = 'huakang-a'
    writeOrderDraft(saved, context, pending)
    expect(readOrderDraft(saved, context)).toBeNull()
    expect(saved.getItem(orderDraftKey(context))).not.toBeNull()
  })

  it.each(['{bad json', JSON.stringify({ submittedOrderNo: 'CT-SAVED' }), 'x'.repeat(128 * 1024 + 1)])(
    'does not restore corrupted, completed or oversized storage', raw => {
      const saved = storage()
      saved.setItem(orderDraftKey(context), raw)
      expect(readOrderDraft(saved, context)).toBeNull()
    },
  )

  it('clears only the current account and factory draft after an explicit discard', () => {
    const saved = storage(), other = { ...context, factoryId: 'huakang-a' }
    const pending = draft()
    pending.master = null
    writeOrderDraft(saved, context, pending)
    writeOrderDraft(saved, other, pending)
    removeOrderDraft(saved, context)
    expect(readOrderDraft(saved, context)).toBeNull()
    expect(readOrderDraft(saved, other)).toEqual(pending)
  })

  it('reports unavailable persistence to its caller and never invents a recovered order', () => {
    const unavailable = {
      getItem: () => { throw new Error('storage unavailable') },
      setItem: () => { throw new Error('storage unavailable') },
      removeItem: () => { throw new Error('storage unavailable') },
    }
    expect(readOrderDraft(unavailable, context)).toBeNull()
    expect(() => writeOrderDraft(unavailable, context, draft())).toThrow('storage unavailable')
    expect(() => removeOrderDraft(unavailable, context)).toThrow('storage unavailable')
  })
})
