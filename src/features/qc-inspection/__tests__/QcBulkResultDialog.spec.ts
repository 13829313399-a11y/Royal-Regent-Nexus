// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { computed } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { qcInspectionApi, type QcInspectionOrder, type QcInspectionEvent } from '@/api/qcInspection'
import { qcInspectionWorkspaceKey } from '../context'
import QcBulkResultDialog from '../QcBulkResultDialog.vue'
import { bulkResultPayload } from '../bulkResults'
vi.mock('@/api/qcInspection', () => ({ qcInspectionApi: { listInspectionEvents: vi.fn(), createInspectionEvent: vi.fn(), updateInspectionEvent: vi.fn() }, createQcRequestId: vi.fn(() => crypto.randomUUID()) }))
const order = (id: string) => ({ id, factory_id: 'huaxing', revision: 3, customer_po_no: '0012', customer_item_no: '0034', quantity: '1200.5', customer_name: 'WMC', sales_contract_no: 'SC1', product_name: 'Toy' }) as QcInspectionOrder
beforeEach(() => { vi.clearAllMocks(); HTMLDialogElement.prototype.showModal = vi.fn(); vi.mocked(qcInspectionApi.listInspectionEvents).mockResolvedValue([]) })
function render(writable = true) { return mount(QcBulkResultDialog, { props: { orders: [order('a'), order('b')] }, global: { provide: { [qcInspectionWorkspaceKey as symbol]: { canResultWrite: computed(() => writable) } } } }) }
async function fill(wrapper: ReturnType<typeof render>) {
  await wrapper.get('input[type=date]').setValue('2026-09-17')
  await wrapper.findAll('select')[0]!.setValue('PASS')
  await wrapper.findAll('select')[1]!.setValue('SELF')
  await wrapper.get('textarea').setValue('本批自检完成')
}
describe('QC bulk results', () => {
  it('requires explicit result/type/date and permission before writing', async () => {
    const wrapper = render(); await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(qcInspectionApi.listInspectionEvents).not.toHaveBeenCalled()
    const readonly = render(false); await fill(readonly); await readonly.get('form').trigger('submit'); await flushPromises()
    expect(qcInspectionApi.createInspectionEvent).not.toHaveBeenCalled()
  })
  it('retains partial successes and retries exactly the same request without creating duplicate successful events', async () => {
    vi.mocked(qcInspectionApi.createInspectionEvent).mockResolvedValueOnce({ id: 'event-a' } as QcInspectionEvent).mockRejectedValueOnce(new Error('network')).mockResolvedValueOnce({ id: 'event-b' } as QcInspectionEvent)
    const wrapper = render(); await fill(wrapper); await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.text()).toContain('已保存 1 / 2 条')
    expect(wrapper.emitted('saved')).toEqual([[['a']]])
    await wrapper.get('form').trigger('submit'); await flushPromises()
    const calls = vi.mocked(qcInspectionApi.createInspectionEvent).mock.calls
    expect(calls).toHaveLength(3); expect(calls[1]).toEqual(calls[2])
    expect(calls[0]![1]).toMatchObject({ factory_id: 'huaxing', expected_pending_order_revision: 3, event_type: 'SELF', inspection_result: 'PASS', actual_inspection_date: '2026-09-17' })
    expect(calls[0]![1].lines[0]).toMatchObject({ customer_po_no: '0012', inspected_quantity: null, order_quantity: '1200.5' })
    expect(wrapper.text()).toContain('本批验货结果已全部保存')
  })
  it('preserves the latest pending draft type, PO lines, defects, tests and dispositions', async () => {
    const base = bulkResultPayload(order('a'), { date: '2026-09-16', result: 'PENDING', eventType: 'LINE', inspector: '原验货员', note: '原说明' })
    const draft = { ...base, id: 'draft', revision: 4, attempt_no: 1, defects: [{ category: '包装', severity: 'MINOR', quantity: 1, description: '原缺陷' }], minor_defect_count: 1, tests: [{ test_item: '跌落测试' }], dispositions: [{ disposition_type: 'ON_HOLD' }] } as QcInspectionEvent
    vi.mocked(qcInspectionApi.listInspectionEvents).mockImplementation(async id => id === 'a' ? [draft] : [])
    vi.mocked(qcInspectionApi.updateInspectionEvent).mockResolvedValue(draft)
    vi.mocked(qcInspectionApi.createInspectionEvent).mockResolvedValue({} as QcInspectionEvent)
    const wrapper = render(); await fill(wrapper); await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(qcInspectionApi.updateInspectionEvent).toHaveBeenCalledWith('a', 'draft', expect.objectContaining({ event_type: 'LINE', expected_revision: 4, expected_pending_order_revision: 3, inspector_name: '原验货员', note: '原说明\n本批自检完成', lines: base.lines, defects: draft.defects, tests: draft.tests, dispositions: draft.dispositions }), expect.any(String))
  })
  it('does not overwrite a submitted event discovered after selection', async () => {
    vi.mocked(qcInspectionApi.listInspectionEvents).mockResolvedValue([{ id: 'done', inspection_result: 'FAIL', attempt_no: 1 } as QcInspectionEvent])
    const wrapper = render(); await fill(wrapper); await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(qcInspectionApi.createInspectionEvent).not.toHaveBeenCalled(); expect(qcInspectionApi.updateInspectionEvent).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('已有验货结果，请打开订单详情核对')
  })
})
