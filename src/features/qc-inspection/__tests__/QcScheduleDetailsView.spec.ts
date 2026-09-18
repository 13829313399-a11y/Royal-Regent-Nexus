// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { computed, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { qcInspectionApi, type QcInspectionOrder } from '@/api/qcInspection'
import { qcInspectionWorkspaceKey } from '../context'
import QcScheduleDetailsView from '../QcScheduleDetailsView.vue'
const route = vi.hoisted(() => ({ name: 'qc-inspection-schedule-details' }))
vi.mock('vue-router', () => ({ useRoute: () => route, RouterLink: { template: '<a><slot /></a>' } }))
vi.mock('@/api/qcInspection', () => ({ qcInspectionApi: { listOrders: vi.fn() } }))
const makeOrder = (id: string, changes: Partial<QcInspectionOrder> = {}) => ({ id, inspection_no: id, source_type: 'SCHEDULE_IMPORT', status: 'SCHEDULED', inspection_result: 'PENDING', customer_name: 'WMC', week_key: '2026-W40', planned_inspection_date: '2026-09-17', ...changes }) as QcInspectionOrder
const dataset = [makeOrder('import-pending'), makeOrder('manual', { source_type: 'MANUAL' }), makeOrder('completed', { status: 'COMPLETED', inspection_result: 'PASS' }), makeOrder('cancelled', { status: 'CANCELLED' })]
beforeEach(() => { vi.clearAllMocks(); vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-09-17T01:00:00Z')); route.name = 'qc-inspection-schedule-details'; vi.mocked(qcInspectionApi.listOrders).mockResolvedValue(structuredClone(dataset)) })
afterEach(() => vi.useRealTimers())
function render(writable = false) {
  const workspace = ref({})
  const wrapper = mount(QcScheduleDetailsView, { global: { stubs: { QcBulkResultDialog: true }, provide: { [qcInspectionWorkspaceKey as symbol]: {
    workspace, factoryId: computed(() => 'huaxing'), weekKey: computed(() => '2026-W38'), canOrderWrite: computed(() => false), canResultWrite: computed(() => writable),
  } } } })
  return { wrapper, workspace }
}
async function button(wrapper: ReturnType<typeof render>['wrapper'], text: string) { await wrapper.findAll('button').find(b => b.text() === text)!.trigger('click') }
describe('daily pending inspection schedule', () => {
  it('defaults to today in Shanghai, excluding manual and completed orders regardless of business week', async () => {
    const { wrapper } = render(); await flushPromises()
    expect(qcInspectionApi.listOrders).toHaveBeenCalledWith('huaxing')
    expect(wrapper.get('input[aria-label="查看日期"]').element).toHaveProperty('value', '2026-09-17')
    const body = wrapper.get('tbody').text()
    expect(body).toContain('import-pending'); expect(body).not.toContain('manual'); expect(body).not.toContain('completed'); expect(body).not.toContain('cancelled')
    await wrapper.get('input[aria-label="仅当前业务周"]').setValue(true)
    expect(wrapper.find('tbody').exists()).toBe(false)
  })
  it('groups full days without splitting 31 rows, uses shipment fallback, and keeps undated orders accessible', async () => {
    vi.mocked(qcInspectionApi.listOrders).mockResolvedValue([
      ...Array.from({ length: 31 }, (_, i) => makeOrder(`same-day-${i}`)),
      makeOrder('fallback', { planned_inspection_date: '', shipment_date: '2026-09-18' }),
      makeOrder('undated', { planned_inspection_date: '' }),
    ])
    const { wrapper } = render(); await flushPromises()
    expect(wrapper.findAll('tbody tr')).toHaveLength(31)
    await wrapper.get('button[aria-label="后一天"]').trigger('click')
    expect(wrapper.get('tbody').text()).toContain('fallback'); expect(wrapper.get('tbody').text()).toContain('按走货日期排期')
    await button(wrapper, '全部日期')
    expect(wrapper.findAll('.qc-day-card')).toHaveLength(3)
    expect(wrapper.findAll('tbody')[0]!.findAll('tr')).toHaveLength(31)
    await button(wrapper, '待安排日期')
    expect(wrapper.findAll('tbody tr')).toHaveLength(1); expect(wrapper.get('tbody').text()).toContain('undated')
  })
  it('selects only filtered orders, clears selections when switching filters and hides bulk actions for read-only users', async () => {
    vi.mocked(qcInspectionApi.listOrders).mockResolvedValue([makeOrder('a'), makeOrder('b', { customer_name: 'WMU' })])
    const { wrapper } = render(true); await flushPromises()
    await wrapper.get('input[aria-label="选择 2026-09-17 全部订单"]').setValue(true)
    expect(wrapper.text()).toContain('已选 2 条')
    await wrapper.get('input[list="qc-schedule-customers"]').setValue('WMU')
    expect(wrapper.text()).toContain('已选 0 条')
    await wrapper.get('input[aria-label="选择订单 b"]').setValue(true)
    await button(wrapper, '批量填写验货结果')
    expect(wrapper.findComponent({ name: 'QcBulkResultDialog' }).props('orders').map((o: QcInspectionOrder) => o.id)).toEqual(['b'])
    const readonly = render(); await flushPromises()
    expect(readonly.wrapper.text()).not.toContain('批量填写验货结果')
  })
  it('validates date ranges and filters on effective dates', async () => {
    vi.mocked(qcInspectionApi.listOrders).mockResolvedValue([makeOrder('a'), makeOrder('b', { planned_inspection_date: '', shipment_date: '2026-09-18' })])
    const { wrapper } = render(); await flushPromises(); await button(wrapper, '日期范围')
    await wrapper.findAll('input[type=date]')[0]!.setValue('2026-09-18')
    await wrapper.findAll('input[type=date]')[1]!.setValue('2026-09-18')
    expect(wrapper.findAll('tbody tr')).toHaveLength(1); expect(wrapper.get('tbody').text()).toContain('b')
    await wrapper.findAll('input[type=date]')[0]!.setValue('2026-09-19')
    expect(wrapper.get('[role=alert]').text()).toContain('开始日期不能晚于结束日期')
    expect(wrapper.find('tbody').exists()).toBe(false)
  })
  it('removes completed orders after refresh and keeps all history on the records route', async () => {
    const { wrapper, workspace } = render(); await flushPromises()
    vi.mocked(qcInspectionApi.listOrders).mockResolvedValue(dataset.map(order => ({ ...order, status: 'COMPLETED', inspection_result: 'FAIL' })))
    workspace.value = { updated: true }; await flushPromises()
    expect(wrapper.text()).toContain('暂无已导入的待验排期')
    route.name = 'qc-inspection-order-records'; vi.mocked(qcInspectionApi.listOrders).mockResolvedValue(dataset)
    const history = render(); await flushPromises()
    for (const order of dataset) expect(history.wrapper.get('tbody').text()).toContain(order.id)
    expect(history.wrapper.text()).not.toContain('批量填写验货结果')
  })
})
