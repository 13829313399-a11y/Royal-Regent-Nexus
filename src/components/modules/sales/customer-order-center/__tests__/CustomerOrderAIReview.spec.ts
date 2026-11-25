import { mount, enableAutoUnmount } from '@vue/test-utils'
import { afterEach, describe, it, expect } from 'vitest'
import CustomerOrderAIReview from '../CustomerOrderAIReview.vue'
import type { CustomerOrderImportPreview } from '@/types/customerOrder'

enableAutoUnmount(afterEach)
function preview(state: 'complete' | 'partial' | 'unavailable' = 'complete') {
  return {
    po_file_name: 'PO.xlsx', rows: [],
    ai_recognition: { state, files: 2, completed: state === 'complete' ? 2 : state === 'partial' ? 1 : 0,
      snapshot_digest: 'fixture', models: ['test'], documents: [
        { file: 'PO.xlsx', state: 'unavailable', message: '千问连接超时，原识别保留', notes: [] },
      ], unmatched: [{ file: 'PO.xlsx', document_kind: 'purchase_order',
        fields: { product_no: '000001-AW', quantity: '100' }, evidence: {
          product_no: { source: 'S1!A1', quote: '000001-AW', text_verified: true },
          quantity: { source: 'P1', quote: 'Quantity 100', text_verified: false },
        } }],
    },
  } as CustomerOrderImportPreview
}
describe('order AI evidence', () => {
  it('stays absent when AI is disabled', () => {
    const w = mount(CustomerOrderAIReview, { props: { preview: { rows: [] } as unknown as CustomerOrderImportPreview } })
    expect(w.find('[data-testid=ai-review]').exists()).toBe(false)
  })
  it.each(['partial', 'unavailable'] as const)('shows %s status without a blocking acknowledgement', state => {
    const w = mount(CustomerOrderAIReview, { props: { preview: preview(state) } })
    expect(w.text()).toContain(state === 'partial' ? '部分完成' : '沿用原识别')
    expect(w.text()).toContain('可以直接保存和生成')
    expect(w.text()).toContain('千问连接超时')
    expect(w.find('input[type=checkbox]').exists()).toBe(false)
  })
  it('expands complete identifiers and differentiates quoted text from image guesses', async () => {
    const w = mount(CustomerOrderAIReview, { props: { preview: preview() } })
    await w.get('button').trigger('click')
    expect(w.text()).toContain('000001-AW')
    expect(w.text()).toContain('S1!A1')
    expect(w.text()).toContain('Quantity 100')
    expect(w.text()).toContain('尚未独立验证')
    expect(w.text()).toContain('未自动加单、合并或取消订单')
    expect(w.get('button').attributes('aria-expanded')).toBe('true')
  })
})
