import { describe, expect, it } from 'vitest'
import { orderSubmissionFor } from '../orderSubmission'
import { readOrderDraft, writeOrderDraft, type OrderDraft } from '../orderDraft'

describe('carton creation retries', () => {
  it('reuses a request after an uncertain response, including reordered object keys', () => {
    const first = orderSubmissionFor({ factory_id: 'huaxing', lines: [{ unit: '个', quantity: 12 }] }, null)
    expect(orderSubmissionFor({ lines: [{ quantity: 12, unit: '个' }], factory_id: 'huaxing' }, first)).toBe(first)
    expect(orderSubmissionFor({ factory_id: 'huaxing', lines: [{ unit: '个', quantity: 13 }] }, first).requestId).toBe(first.requestId)
    // Refreshing master dates/customer names must not split an uncertain request into a new order.
    expect(orderSubmissionFor({ factory_id: 'huaxing', customer_name: '新名称', due_date: '2026-10-25' }, first).requestId).toBe(first.requestId)
    expect(orderSubmissionFor({ factory_id: 'huaxing', lines: [{ unit: '个', quantity: 12 }] }, null).requestId).not.toBe(first.requestId)
  })

  it('persists the unresolved request with its scoped draft and rejects malformed identifiers', () => {
    const context = { userId: 'warehouse', employmentEpoch: 1, factoryId: 'huaxing' }
    const values = new Map<string, string>()
    const storage = { getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => { values.set(key, value) } }
    const draft: OrderDraft = { form: { customerPo: '', quantityBasis: 'CALCULATED', customerCode: '', supplierId: '',
      contractNo: '', itemNo: '', productName: '', orderQuantity: '', orderDate: '', customerDueDate: '', dueDate: '', note: '',
      materials: [{ id: 'line', packagingType: '', paperQuality: '', specification: '', unitsPerCarton: '', unit: '个', dimensionUnit: 'cm',
        unitPrice: 0, currency: 'CNY', priceSource: 'manual', note: '' }] }, copiedOrderNo: '', master: null, history: null, schedule: null,
      submission: orderSubmissionFor({ customer_po: '', quantity: 12 }, null) }
    writeOrderDraft(storage, context, draft)
    const restored = readOrderDraft(storage, context)!
    expect(orderSubmissionFor({ quantity: 12, customer_po: '' }, restored.submission!).requestId).toBe(draft.submission!.requestId)
    expect(readOrderDraft(storage, { ...context, userId: 'other' })).toBeNull()
    draft.submission = orderSubmissionFor({ lines: [{ note: 'x'.repeat(15000) }, { note: 'y'.repeat(15000) }] }, null)
    writeOrderDraft(storage, context, draft)
    expect(readOrderDraft(storage, context)?.submission).toEqual(draft.submission)
    draft.submission!.requestId = 'invalid/id'
    writeOrderDraft(storage, context, draft)
    expect(readOrderDraft(storage, context)).toBeNull()
  })
})
