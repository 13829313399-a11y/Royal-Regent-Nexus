import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { api, auth } = vi.hoisted(() => ({
  api: {
    collection: vi.fn(), dashboard: vi.fn(), audit: vi.fn(), deletedRecords: vi.fn(), restoreRecord: vi.fn(),
    createRecord: vi.fn(), updateRecord: vi.fn(), deleteRecord: vi.fn(), setDayOff: vi.fn(),
  },
  auth: { can: vi.fn(() => true) },
}))
vi.mock('@/api/threeDPrinting', () => ({ threeDPrintingApi: api }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))
vi.mock('@/stores/app', () => ({ useAppStore: () => ({ activeProductionFactory: { id: 'huakang-a' } }) }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/lib/http', () => ({ getApiErrorMessage: (error: Error) => error.message }))

import View from '@/views/ThreeDPrintingManagementView.vue'

const record = {
  id: 'record-pr04', factory_id: 'huakang-a', business_date: '2026-09-04', machine_no: 1,
  product_name: '历史产品', material_name: 'PLA', weight_g: 100, quantity: 2, duration_hours: 1,
  status: 'running', product_id: '', quoted_price: 50, design_fee: 0, customer: '', remark: '',
  revision: 3, material_status: 'material_shortage', inventory_consumed: false,
  data_quality_flags: ['material_shortage'], cost_profile_version: 'nexus-v1-test',
  calculated_cost_snapshot: {}, frozen_totals: {}, deleted_at: '',
}

const data = () => ({
  factory_id: 'huakang-a', generated_at: '', printers: [], materials: [], products: [],
  records: [{ ...record }], inventory: [], inventory_movements: [], schedules: [], maintenance: [],
  day_off_dates: [], day_statuses: [], summary: { incompleteCostRecordCount: 1 },
  settings: { revision: 1, machine_count: 11, material_loss_rate: 1.2, profit_rate_percent: 40,
    labor_per_day: 220, electricity_per_machine_day: 1.5 },
})

let wrapper: ReturnType<typeof mount>
const button = (text: string) => wrapper.findAll('button').find(item => item.text() === text)!

beforeEach(() => {
  vi.clearAllMocks()
  auth.can.mockReturnValue(true)
  api.dashboard.mockResolvedValue(data())
  api.collection.mockImplementation(async (kind: string) => ({ items: kind === 'records' ? data().records : [], total: kind === 'records' ? 1 : 0, page: 1, page_size: 50 }))
  api.audit.mockResolvedValue([])
  api.deletedRecords.mockResolvedValue([{ ...record, revision: 4, deleted_at: '2026-09-04' }])
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  vi.spyOn(window, 'prompt').mockReturnValue('核对后恢复')
})

afterEach(() => {
  wrapper?.unmount()
  vi.restoreAllMocks()
})

describe('3D history and ledger operations', () => {
  it('shows a stale site without remote controls and keeps open production records', async () => {
    api.dashboard.mockResolvedValue({ ...data(), network_health: {
      configured: true, status: 'unreachable', observed_at: '2026-09-04T08:00:00Z',
      failed_machine_numbers: [1], message: '站点VPN不可达，暂停远程指令，开放任务等待对账',
    }, printers: [{ id: 'printer-1', machine_no: 1, name: '1号机', connected: false,
      state: 'STALE', status_stale: true, progress: 40, remaining_minutes: 30,
      nozzle_temperature: 20, bed_temperature: 20, current_file: 'test.3mf', last_seen_at: '',
    }] })
    wrapper = mount(View)
    await flushPromises()
    expect(wrapper.text()).toContain('河源站点网络')
    expect(wrapper.text()).toContain('开放任务等待对账')
    expect(wrapper.text()).toContain('状态陈旧')
    expect(button('远程暂停')).toBeUndefined()
    expect(button('恢复打印')).toBeUndefined()
    await button('生产记录').trigger('click')
    expect(wrapper.text()).toContain('历史产品')
    expect(api.updateRecord).not.toHaveBeenCalled()
  })

  it('shows incomplete cost and shortage, and sends revision/reason when deleting', async () => {
    wrapper = mount(View)
    await flushPromises()
    expect(wrapper.text()).toContain('1 条记录缺少完整历史成本')
    await button('生产记录').trigger('click')
    expect(wrapper.text()).toContain('缺料 · 未扣库存')
    await button('撤销').trigger('click')
    await flushPromises()
    expect(api.deleteRecord).toHaveBeenCalledWith('record-pr04', 3, '核对后恢复', 'delete-record-pr04-3')
  })

  it('restores from audit with the tombstone revision and refreshes the list', async () => {
    wrapper = mount(View)
    await flushPromises()
    await button('设置与审计').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('已撤销记录')
    await button('恢复记录').trigger('click')
    await flushPromises()
    expect(api.restoreRecord).toHaveBeenCalledWith('record-pr04', 4, '核对后恢复', 'restore-record-pr04-4')
    expect(api.deletedRecords).toHaveBeenCalledTimes(2)
  })

  it('preserves the request key on retry and uses a fresh key for the next record', async () => {
    api.createRecord.mockRejectedValueOnce(new Error('网络中断')).mockResolvedValue({})
    wrapper = mount(View)
    await flushPromises()
    await button('生产记录').trigger('click')
    const form = wrapper.get('form.panel-card')
    await form.trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('网络中断')
    await form.trigger('submit')
    await flushPromises()
    const firstKey = api.createRecord.mock.calls[0]![0].idempotency_key
    expect(api.createRecord.mock.calls[1]![0].idempotency_key).toBe(firstKey)
    await form.trigger('submit')
    await flushPromises()
    expect(api.createRecord.mock.calls[2]![0].idempotency_key).not.toBe(firstKey)
  })

  it('does not expose audit recovery to an operator without audit access', async () => {
    auth.can.mockImplementation((...args: unknown[]) => args[0] !== 'three_d_printing:audit_read')
    wrapper = mount(View)
    await flushPromises()
    await button('设置与审计').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('当前岗位无审计查看权限')
    expect(api.deletedRecords).not.toHaveBeenCalled()
    expect(button('恢复记录')).toBeUndefined()
  })
})
