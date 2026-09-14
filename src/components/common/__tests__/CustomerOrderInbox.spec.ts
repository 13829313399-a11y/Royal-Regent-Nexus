import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CustomerOrderInbox from '../CustomerOrderInbox.vue'

const httpMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))
const routerReplaceMock = vi.hoisted(() => vi.fn().mockResolvedValue(undefined))
const routeState = vi.hoisted(() => ({
  path: '/modules/pmc-warehouse/customer-order-inbox',
  query: { factory: 'huaxing', recipient: 'pmc' } as Record<string, string>,
}))
const appStoreMock = vi.hoisted(() => ({
  activeProductionFactory: { id: 'huaxing', shortName: '华兴' },
}))

vi.mock('@/lib/http', () => ({
  http: httpMock,
  getApiErrorMessage: (error: unknown) => error instanceof Error ? error.message : 'request failed',
}))

vi.mock('vue-router', () => ({
  useRoute: () => routeState,
  useRouter: () => ({ replace: routerReplaceMock }),
}))

vi.mock('@/stores/app', () => ({
  useAppStore: () => appStoreMock,
}))

const baseItem = {
  id: 'inbox-1',
  line_id: 'line-1',
  factory_id: 'huaxing',
  recipient: 'pmc',
  version: 2,
  latest_version: 3,
  snapshot: {
    factory_id: 'huaxing',
    customer_code: 'demo',
    customer_name: '测试客户',
    reference_no: 'REF-1',
    product_no: 'ITEM-1',
    po_no: 'PO-1',
    contract_no: 'SC-1',
    product_name_zh: '测试产品',
    quantity: '1000',
    requested_ship_date: '2026-10-01',
    status: 'active',
    version: 2,
    change_reason: '交期调整',
  },
  actor: 'sales',
  created_at: '2026-09-14T01:00:00Z',
  received_at: null,
  received_by: null,
  status: 'sent',
} as const

function configureApi(options: { receive?: boolean; items?: unknown[] } = {}) {
  httpMock.get.mockImplementation((url: string) => {
    if (url.endsWith('/capabilities')) {
      return Promise.resolve({ data: { inbox_read: true, inbox_receive: options.receive ?? true } })
    }
    return Promise.resolve({
      data: {
        items: options.items ?? [baseItem],
        total: options.items?.length ?? 1,
        page: 1,
        page_size: 20,
      },
    })
  })
  httpMock.post.mockResolvedValue({ data: { ...baseItem, status: 'received' } })
}

function mountInbox() {
  return mount(CustomerOrderInbox, { global: { stubs: { LoaderCircle: true } } })
}

describe('CustomerOrderInbox', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routeState.path = '/modules/pmc-warehouse/customer-order-inbox'
    routeState.query = { factory: 'huaxing', recipient: 'pmc' }
    configureApi()
  })

  it('distinguishes historical total from the remaining delivery demand at dispatch', async () => {
    configureApi({ items: [{ ...baseItem, version: 1, latest_version: 1, snapshot: {
      ...baseItem.snapshot, quantity: '100', shipped_quantity: '80', remaining_quantity: '20', history_cutoff_date: '2026-09-01',
    } }] })
    const wrapper = mountInbox()
    await flushPromises()
    expect(wrapper.text()).toContain('历史迁入')
    expect(wrapper.text()).toContain('发送时剩余待交付 20')
    expect(wrapper.text()).toContain('发送时累计已走货 80')
    expect(wrapper.text()).toContain('历史期初截至 2026-09-01')
    wrapper.unmount()
  })

  it('loads a recipient-scoped inbox and keeps versions visible without exposing price data', async () => {
    const wrapper = mountInbox()
    await flushPromises()

    expect(httpMock.get).toHaveBeenCalledWith('/customer-order-ledger/inbox', {
      params: { factory_id: 'huaxing', recipient: 'pmc', page: 1, page_size: 20 },
    })
    expect(wrapper.text()).toContain('测试客户')
    expect(wrapper.text()).toContain('V2')
    expect(wrapper.text()).toContain('变更')
    expect(wrapper.text()).toContain('历史版本，最新 V3')
    expect(wrapper.text()).not.toContain('价格')
    expect(wrapper.text()).toContain('PMC')
    wrapper.unmount()
  })

  it('requires an explicit concrete factory and never falls back from group or invalid routes', async () => {
    routeState.query = { factory: 'group', recipient: 'pmc' }
    const wrapper = mountInbox()
    await flushPromises()

    expect(wrapper.text()).toContain('集团总览或无效厂区不能读取订单收件箱')
    expect(wrapper.text()).toContain('未选择具体厂区')
    expect(httpMock.get).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('expands the customer requirements carried by the order snapshot', async () => {
    const item = {
      ...baseItem,
      snapshot: {
        ...baseItem.snapshot,
        packaging: '彩盒',
        units_per_carton: 12,
        carton_mark: '客户箱唛',
        printing_requirement: '四色印刷',
      },
    }
    configureApi({ items: [item] })
    const wrapper = mountInbox()
    await flushPromises()

    await wrapper.get('button.requirement-button').trigger('click')
    expect(wrapper.text()).toContain('客户箱唛')
    expect(wrapper.text()).toContain('四色印刷')
    expect(wrapper.text()).toContain('彩盒')
    expect(wrapper.text()).toContain('每箱数量')
    wrapper.unmount()
  })

  it('posts an idempotent receive request with no body', async () => {
    const wrapper = mountInbox()
    await flushPromises()

    await wrapper.get('button.receive-button').trigger('click')
    await flushPromises()

    expect(httpMock.post).toHaveBeenCalledWith(
      '/customer-order-ledger/inbox/inbox-1/receive',
      undefined,
      { params: { factory_id: 'huaxing', recipient: 'pmc' } },
    )
    wrapper.unmount()
  })

  it('shows a clear permission message and disables receive when capability is absent', async () => {
    configureApi({ receive: false })
    const wrapper = mountInbox()
    await flushPromises()

    expect(wrapper.text()).toContain('仅查看或权限待确认')
    expect(wrapper.text()).toContain('没有PMC订单签收权限，仅可查看')
    expect(wrapper.get('button.receive-button').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('clears the previous view and requests the selected recipient', async () => {
    const wrapper = mountInbox()
    await flushPromises()

    await wrapper.findAll('[role="tab"]')[2]!.trigger('click')
    await flushPromises()

    expect(routerReplaceMock).toHaveBeenCalledWith({
      query: { factory: 'huaxing', recipient: 'injection' },
    })
    expect(httpMock.get).toHaveBeenCalledWith('/customer-order-ledger/inbox', {
      params: { factory_id: 'huaxing', recipient: 'injection', page: 1, page_size: 20 },
    })
    wrapper.unmount()
  })
})
