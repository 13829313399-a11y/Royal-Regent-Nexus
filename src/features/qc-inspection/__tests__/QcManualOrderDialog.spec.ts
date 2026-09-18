// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { computed } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { qcInspectionApi, type QcInspectionOrder } from '@/api/qcInspection'
import { qcInspectionWorkspaceKey } from '../context'
import QcManualOrderDialog from '../QcManualOrderDialog.vue'
vi.mock('@/api/qcInspection', () => ({ qcInspectionApi: { createOrder: vi.fn() }, createQcRequestId: () => 'stable-request' }))
beforeEach(() => { vi.clearAllMocks(); HTMLDialogElement.prototype.showModal = vi.fn() })
function render(orders: QcInspectionOrder[] = [], writable = true) {
  return mount(QcManualOrderDialog, { props: { customers: ['WMC'], orders }, global: { provide: { [qcInspectionWorkspaceKey as symbol]: {
    factoryId: computed(() => 'huaxing'), factoryName: computed(() => '华兴'), weekKey: computed(() => '2026-W38'), canOrderWrite: computed(() => writable),
  } } } })
}
async function fill(wrapper: ReturnType<typeof render>) {
  const inputs = wrapper.findAll('input')
  for (const [index, value] of [[0, ' WMC '], [1, ' SC001 '], [2, '000123'], [3, '000456'], [5, '1200.1250']] as const) await inputs[index]!.setValue(value)
  await wrapper.find('textarea').setValue('客户临时预约验货')
}
describe('QC manual order dialog', () => {
  it('preserves identifiers and decimal quantity, permits unscheduled dates, and reuses identity after an uncertain failure', async () => {
    vi.mocked(qcInspectionApi.createOrder).mockRejectedValueOnce(new Error('network')).mockResolvedValueOnce({ id: 'created' } as QcInspectionOrder)
    const wrapper = render(); await fill(wrapper)
    await wrapper.find('form').trigger('submit'); await flushPromises()
    await wrapper.find('form').trigger('submit'); await flushPromises()
    const calls = vi.mocked(qcInspectionApi.createOrder).mock.calls
    expect(calls).toHaveLength(2)
    expect(calls[0]).toEqual(calls[1])
    expect(calls[1]![0]).toMatchObject({ customer_name: 'WMC', customer_po_no: '000123', customer_item_no: '000456', quantity: '1200.1250', planned_inspection_date: '', factory_id: 'huaxing', week_key: '2026-W38', note: '客户临时预约验货' })
    expect(wrapper.emitted('saved')).toEqual([[{ id: 'created' }]])
  })
  it('requires duplicate acknowledgement before saving another inspection', async () => {
    const wrapper = render([{ sales_contract_no: 'SC001', customer_po_no: '000123', customer_item_no: '000456' } as QcInspectionOrder])
    await fill(wrapper); await wrapper.find('form').trigger('submit'); await flushPromises()
    expect(qcInspectionApi.createOrder).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('请先核对已有订单')
  })
  it('does not submit with missing required fields or without write permission', async () => {
    const wrapper = render(); await fill(wrapper)
    await wrapper.findAll('input')[2]!.setValue('   ')
    await wrapper.find('form').trigger('submit'); await flushPromises()
    expect(qcInspectionApi.createOrder).not.toHaveBeenCalled()
    const readonly = render([], false); await fill(readonly)
    await readonly.find('form').trigger('submit'); await flushPromises()
    expect(qcInspectionApi.createOrder).not.toHaveBeenCalled()
  })
})
