import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import Component from '../CartonReceiptDetail.vue'
import type { CartonReceiptResponse } from '@/api/cartonProcurement'
const receipt: CartonReceiptResponse = { id: 'R1', factory_id: 'huaxing', receipt_no: 'RC1', delivery_note_no: '送货-001', delivery_date: '2026-09-10', acceptance_date: '2026-09-10', supplier_id: 'SUP1', supplier_name: '供应商', import_batch_id: null, status: 'POSTED', note: '', revision: 2, created_by: 'keeper', created_by_name: '仓管', confirmed_by: 'keeper', confirmed_by_name: '仓管', created_at: '', updated_at: '', confirmed_at: '', lines: [{ id: 'EXACT-LINE1', line_no: 1, source_type: 'FORMAL_ORDER', order_line_id: 'ORDER-LINE1', customer_code: 'CUSTOMER1', customer_name: '客户', contract_no: 'C1', item_no: 'BOX1', packaging_type: '外箱', paper_quality: 'A33', specification: '30*20*10', delivered_quantity: '10', received_quantity: '10', damaged_quantity: '0', rejected_quantity: '0', unusable_quantity: '0', effective_quantity: '10', unit: '个', unit_price: '2.123456', currency: 'CNY', location: 'A01', feedback_note: '' }] }
it('reports the exact posted receipt paper while preserving and labelling the original voucher price', async () => {
  const w = mount(Component, { props: { receipt, pinned: true, canContinue: false, canReportPrice: true }, global: { stubs: { CartonSourceLinks: true } } })
  expect(w.get('thead').text()).toContain('原凭证单价'); expect(w.text()).toContain('当前生效价与更正进度见'); expect(w.text()).toContain('2.123456')
  await w.get('[aria-label="报告单价错误 EXACT-LINE1"]').trigger('click'); expect(w.emitted('price')?.[0]).toEqual(['EXACT-LINE1']); expect(receipt.lines[0]!.unit_price).toBe('2.123456'); w.unmount()
})
it('offers no price report during hover preview, for an unauthorized user, or for a reversed receipt', () => {
  for (const context of [{ pinned: false, canReportPrice: true, receipt }, { pinned: true, canReportPrice: false, receipt }, { pinned: true, canReportPrice: true, receipt: { ...receipt, status: 'REVERSED' as const } }]) {
    const w = mount(Component, { props: { ...context, canContinue: false }, global: { stubs: { CartonSourceLinks: true } } }); expect(w.find('[aria-label="报告单价错误 EXACT-LINE1"]').exists()).toBe(false); w.unmount()
  }
})
