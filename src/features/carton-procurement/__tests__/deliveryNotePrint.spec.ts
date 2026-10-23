import { expect, it } from 'vitest'
import { deliveryNoteHtml } from '../deliveryNotePrint'
import type { SupplierDocument } from '@/api/cartonSupplierPortal'

const document = (overrides: Partial<SupplierDocument> = {}): SupplierDocument => ({
  id: 'DOC-1', kind: 'DELIVERY', factory_id: 'huaxing', document_no: 'DN-2026-001', document_type: '送货单',
  date: '2026-10-20', created_at: '2026-10-20T09:00:00+08:00', status: 'SENT', replenishment: false, export_count: 0,
  orders: [{ order_no: 'ORDER-1', customer_name: 'Dickie', contract_no: 'SC-1', customer_po: 'PO-9', item_no: 'ITEM-1', product_name: '彩盒', order_date: '2026-09-01', planned_date: '2026-10-20' }],
  lines: [
    { order_no: 'ORDER-1', child_no: 'ORDER-1/01', customer_name: 'Dickie', packaging_type: '外箱', paper_quality: 'A33', specification: '30*20*15', unit: '个', quantity: '100' },
    { order_no: 'ORDER-1', child_no: 'ORDER-1/02', customer_name: 'Dickie', packaging_type: '刀卡', paper_quality: 'A33', specification: '30*20', unit: '张', quantity: '50' },
  ],
  ...overrides,
})

it('renders a standalone A4 delivery note with the document facts', () => {
  const html = deliveryNoteHtml(document(), { supplierName: '河源东康纸品有限公司', factoryName: '华兴' })
  expect(html).toContain('<!doctype html>')
  expect(html).toContain('DN-2026-001')
  expect(html).toContain('河源东康纸品有限公司')
  expect(html).toContain('华兴')
  expect(html).toContain('2026-10-20')
  expect(html).toContain('ORDER-1/01')
  expect(html).toContain('外箱')
  expect(html).toContain('合计：100 个 / 50 张')
  expect(html).toContain('@page { size: A4')
})

it('escapes document text and survives a note without lines', () => {
  const html = deliveryNoteHtml(document({ document_no: 'DN<&>"', lines: [] }), { supplierName: 'A&B', factoryName: '华兴' })
  expect(html).toContain('DN&lt;&amp;&gt;&quot;')
  expect(html).toContain('A&amp;B')
  expect(html).toContain('本单没有纸品明细')
  expect(html).toContain('合计：0')
})
