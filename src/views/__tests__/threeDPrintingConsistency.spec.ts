import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { api, auth } = vi.hoisted(() => ({
  api: {
    collection: vi.fn(), dashboard: vi.fn(), audit: vi.fn(), deletedRecords: vi.fn(), restoreRecord: vi.fn(),
    createRecord: vi.fn(), updateRecord: vi.fn(), deleteRecord: vi.fn(), setDayOff: vi.fn(),
    createProduct: vi.fn(), updateProduct: vi.fn(), uploadProductImage: vi.fn(),
  },
  auth: { can: vi.fn(() => true) },
}))
vi.mock('@/api/threeDPrinting', () => ({ threeDPrintingApi: api }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))
vi.mock('@/stores/app', () => ({ useAppStore: () => ({ activeProductionFactory: { id: 'huakang-a' } }) }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }), RouterLink: { template: '<a><slot /></a>' } }))
vi.mock('@/components/layout/AccountMenu.vue', () => ({ default: { template: '<button>账号与头像设置</button>' } }))
vi.mock('@/lib/http', () => ({ http: { defaults: { baseURL: '/api' } }, getApiErrorMessage: (error: Error) => error.message }))

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
  HTMLDialogElement.prototype.showModal = vi.fn()
  HTMLDialogElement.prototype.close = vi.fn()
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
  vi.unstubAllGlobals()
})

describe('3D history and ledger operations', () => {
  it('pastes a product image, previews it and uploads the same file when saving', async () => {
    const revoke = vi.fn()
    vi.stubGlobal('URL', class extends URL {
      static createObjectURL = vi.fn(() => 'blob:product-preview')
      static revokeObjectURL = revoke
    })
    api.createProduct.mockResolvedValue({ id: 'new-product', revision: 1 })
    api.uploadProductImage.mockResolvedValue({})
    wrapper = mount(View)
    await flushPromises()
    await button('产品库').trigger('click')
    await flushPromises()
    await button('+ 添加产品').trigger('click')
    const name = wrapper.get('dialog input[required]')
    await name.setValue('粘贴图片产品')
    const file = new File(['png'], 'clipboard.png', { type: 'image/png' })
    const event = new Event('paste', { bubbles: true, cancelable: true })
    Object.defineProperty(event, 'clipboardData', { value: { items: [{ kind: 'file', type: file.type, getAsFile: () => file }] } })
    wrapper.get('button[aria-label="关闭"]').element.dispatchEvent(event)
    await flushPromises()
    expect(event.defaultPrevented).toBe(true)
    expect(wrapper.get('img[alt="产品图片预览"]').attributes('src')).toBe('blob:product-preview')
    expect(api.uploadProductImage).not.toHaveBeenCalled()
    await wrapper.get('dialog form').trigger('submit')
    await flushPromises()
    expect(api.createProduct).toHaveBeenCalledWith(expect.objectContaining({ name: '粘贴图片产品' }))
    expect(api.uploadProductImage).toHaveBeenCalledWith('new-product', file)
    expect(revoke).toHaveBeenCalledWith('blob:product-preview')
    expect(wrapper.find('dialog').exists()).toBe(false)
  })

  it('preserves text paste and lets users cancel an image without uploading', async () => {
    const revoke = vi.fn()
    vi.stubGlobal('URL', class extends URL {
      static createObjectURL = vi.fn(() => 'blob:cancel-preview')
      static revokeObjectURL = revoke
    })
    wrapper = mount(View)
    await flushPromises()
    await button('产品库').trigger('click')
    await flushPromises()
    await button('+ 添加产品').trigger('click')
    const zone = wrapper.get('[aria-label="产品图片粘贴区"]')
    const textEvent = new Event('paste', { bubbles: true, cancelable: true })
    Object.defineProperty(textEvent, 'clipboardData', { value: { items: [{ kind: 'string', type: 'text/plain' }] } })
    zone.element.dispatchEvent(textEvent)
    expect(textEvent.defaultPrevented).toBe(false)
    const file = new File(['image'], 'screen.png', { type: 'image/png' })
    await zone.trigger('paste', { clipboardData: { items: [{ kind: 'file', type: file.type, getAsFile: () => file }] } })
    expect(wrapper.find('img[alt="产品图片预览"]').exists()).toBe(true)
    const oversized = new File([new Uint8Array(5 * 1024 * 1024 + 1)], 'large.png', { type: 'image/png' })
    await zone.trigger('paste', { clipboardData: { items: [{ kind: 'file', type: oversized.type, getAsFile: () => oversized }] } })
    expect(wrapper.text()).toContain('图片超过 5MB')
    expect(wrapper.get('img[alt="产品图片预览"]').attributes('src')).toBe('blob:cancel-preview')
    await button('取消本次图片').trigger('click')
    await flushPromises()
    expect(wrapper.find('img[alt="产品图片预览"]').exists()).toBe(false)
    expect(revoke).toHaveBeenCalledWith('blob:cancel-preview')
    expect(api.uploadProductImage).not.toHaveBeenCalled()
  })

  it('searches historical product records across pages, keeps the keyword and restores daily mode', async () => {
    wrapper = mount(View)
    await flushPromises()
    await button('每日记录').trigger('click')
    await flushPromises()
    api.collection.mockImplementation(async (kind, params) => ({
      items: kind === 'records' ? [{ ...record, product_name: '河马头', business_date: '2026-08-12' }] : [],
      total: 121, page: params.page, page_size: 50,
    }))
    await wrapper.get('input[aria-label="打印记录产品关键词"]').setValue(' 河马 ')
    api.collection.mockRejectedValueOnce(new Error('查询超时，请重试'))
    await wrapper.get('form[aria-label="打印记录搜索"]').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('查询超时，请重试')
    await wrapper.get('form[aria-label="打印记录搜索"]').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).not.toContain('查询超时，请重试')
    expect(api.collection).toHaveBeenLastCalledWith('records', expect.objectContaining({
      q: '河马', date_from: '', date_to: '', page: 1,
    }))
    expect(wrapper.text()).toContain('全部历史 · 打印记录')
    expect(wrapper.text()).toContain('2026-08-12')
    await button('末页').trigger('click')
    await flushPromises()
    expect(api.collection).toHaveBeenLastCalledWith('records', expect.objectContaining({ q: '河马', page: 3, date_from: '' }))
    await wrapper.get('form[aria-label="打印记录搜索"] input[type="checkbox"]').setValue(false)
    await button('搜索记录').trigger('click')
    await wrapper.get('form[aria-label="打印记录搜索"]').trigger('submit')
    await flushPromises()
    const last = api.collection.mock.calls.at(-1)![1]
    expect(last.date_from).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    expect(last.date_to).toBe(last.date_from)
    expect(last.page).toBe(1)
    await button('返回当日记录').trigger('click')
    await flushPromises()
    expect(api.collection).toHaveBeenLastCalledWith('records', expect.objectContaining({ q: '', page: 1 }))
    expect(button('返回当日记录')).toBeUndefined()
  })

  it('opens related historical records directly from the product library', async () => {
    api.collection.mockImplementation(async (kind: string) => ({
      items: kind === 'products' ? [{ id: 'product-1', name: '河马头', customer: '客户甲' }] : [],
      total: kind === 'products' ? 1 : 0, page: 1, page_size: 50,
    }))
    wrapper = mount(View)
    await flushPromises()
    await button('产品库').trigger('click')
    await flushPromises()
    await button('打印记录').trigger('click')
    await flushPromises()
    expect(api.collection).toHaveBeenLastCalledWith('records', expect.objectContaining({ q: '河马头', date_from: '', date_to: '', page: 1 }))
    expect(wrapper.text()).toContain('全部历史 · 打印记录')
  })

  it('does not overwrite a live printer snapshot with a slower dashboard response', async () => {
    class Stream extends EventTarget {
      static latest: Stream
      constructor() { super(); Stream.latest = this }
      close() {}
    }
    vi.stubGlobal('EventSource', Stream)
    wrapper = mount(View)
    await flushPromises()
    await button('每日记录').trigger('click')
    let resolve!: (value: ReturnType<typeof data>) => void
    api.dashboard.mockImplementationOnce(() => new Promise(done => { resolve = done }))
    await wrapper.get('button[aria-label="刷新数据"]').trigger('click')
    Stream.latest.dispatchEvent(new MessageEvent('snapshot', { data: JSON.stringify({
      printers: [{ id: 'p1', machine_no: 1, connected: true, state: 'RUNNING',
        current_file: '刚收到的新打印任务', progress_percent: 42, remaining_minutes: 10 }],
      run_version: 'fresh',
    }) }))
    await flushPromises()
    expect(wrapper.text()).toContain('刚收到的新打印任务')
    expect(wrapper.text()).toContain('实时同步中')
    resolve(data()) // The old query has no printers.
    await flushPromises()
    expect(wrapper.text()).toContain('刚收到的新打印任务')
    expect(wrapper.text()).toContain('打印中')
  })

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
    expect(wrapper.text()).toContain('网络检测提示')
    await button('机器状态').trigger('click')
    expect(wrapper.text()).toContain('离线')
    expect(button('远程暂停')).toBeUndefined()
    expect(button('恢复打印')).toBeUndefined()
    await button('每日记录').trigger('click')
    expect(wrapper.text()).toContain('历史产品')
    expect(api.updateRecord).not.toHaveBeenCalled()
  })

  it('refreshes after a save even while an older dashboard query is pending', async () => {
    wrapper = mount(View)
    await flushPromises()
    await button('每日记录').trigger('click')
    await flushPromises()
    let resolveOld!: (value: ReturnType<typeof data>) => void
    api.dashboard.mockImplementationOnce(() => new Promise(done => { resolveOld = done }))
    await wrapper.get('button[aria-label="刷新数据"]').trigger('click')
    api.dashboard.mockResolvedValue({ ...data(), summary: { incompleteCostRecordCount: 1 },
      records: [], settings: { ...data().settings, revision: 9 } })
    api.deleteRecord.mockResolvedValue({})
    api.collection.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 })
    const beforeSave = api.dashboard.mock.calls.length
    await button('删除').trigger('click')
    await flushPromises()
    expect(api.dashboard.mock.calls.length).toBeGreaterThan(beforeSave)
    resolveOld(data())
    await flushPromises()
    expect(wrapper.text()).not.toContain('历史产品')
  })

  it('shows incomplete cost and shortage, and sends revision/reason when deleting', async () => {
    wrapper = mount(View)
    await flushPromises()
    expect(wrapper.text()).toContain('仪表盘')
    await button('每日记录').trigger('click')
    expect(wrapper.text()).toContain('历史产品')
    await button('删除').trigger('click')
    await flushPromises()
    expect(api.deleteRecord).toHaveBeenCalledWith('record-pr04', 3, '核对后恢复', 'delete-record-pr04-3')
  })

  it('restores from audit with the tombstone revision and refreshes the list', async () => {
    wrapper = mount(View)
    await flushPromises()
    await button('设置').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('已撤销记录')
    await button('恢复记录').trigger('click')
    await flushPromises()
    expect(api.restoreRecord).toHaveBeenCalledWith('record-pr04', 4, '核对后恢复', 'restore-record-pr04-4')
    expect(api.deletedRecords).toHaveBeenCalledTimes(2)
  })

  it('renders without native randomUUID and preserves retry keys while rotating after success', async () => {
    vi.stubGlobal('crypto', {
      getRandomValues: globalThis.crypto.getRandomValues.bind(globalThis.crypto),
    })
    api.createRecord.mockRejectedValueOnce(new Error('网络中断')).mockResolvedValue({})
    wrapper = mount(View)
    await flushPromises()
    await button('每日记录').trigger('click')
    await flushPromises()
    await button('+ 添加记录').trigger('click')
    const form = wrapper.get('form.panel-card')
    await form.trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('网络中断')
    await form.trigger('submit')
    await flushPromises()
    const firstKey = api.createRecord.mock.calls[0]![0].idempotency_key
    expect(firstKey).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
    expect(api.createRecord.mock.calls[1]![0].idempotency_key).toBe(firstKey)
    await button('+ 添加记录').trigger('click')
    await wrapper.get('form.panel-card').trigger('submit')
    await flushPromises()
    expect(api.createRecord.mock.calls[2]![0].idempotency_key).not.toBe(firstKey)
  })

  it('does not expose audit recovery to an operator without audit access', async () => {
    auth.can.mockImplementation((...args: unknown[]) => args[0] !== 'three_d_printing:audit_read')
    wrapper = mount(View)
    await flushPromises()
    await button('设置').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('当前岗位无审计查看权限')
    expect(api.deletedRecords).not.toHaveBeenCalled()
    expect(button('恢复记录')).toBeUndefined()
  })
})
