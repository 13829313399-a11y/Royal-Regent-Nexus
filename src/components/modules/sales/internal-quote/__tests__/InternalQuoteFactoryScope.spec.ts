import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AuthMeResponse } from '@/api/auth'
import type { ApiInternalQuote, ApiInternalQuoteCustomer, ApiInternalQuotePricingBaseline } from '@/api/internalQuote'
import InternalQuoteBaselineDialog from '@/components/modules/sales/internal-quote/InternalQuoteBaselineDialog.vue'
import InternalQuoteCreateDialog from '@/components/modules/sales/internal-quote/InternalQuoteCreateDialog.vue'
import InternalQuoteCustomerDialog from '@/components/modules/sales/internal-quote/InternalQuoteCustomerDialog.vue'
import InternalQuoteHome from '@/components/modules/sales/internal-quote/InternalQuoteHome.vue'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import type { InternalQuoteCreatePayload } from '@/types/internalQuoteDesk'

const routerPushMock = vi.hoisted(() => vi.fn())
const internalQuoteApiMock = vi.hoisted(() => ({
  list: vi.fn(),
  listBusinessOwners: vi.fn(),
  listCustomers: vi.fn(),
  createCustomer: vi.fn(),
  updateCustomer: vi.fn(),
  deleteCustomer: vi.fn(),
  create: vi.fn(),
  clone: vi.fn(),
  getPricingBaseline: vi.fn(),
  updatePricingBaseline: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPushMock }),
}))

vi.mock('@/api/internalQuote', () => ({
  internalQuoteApi: internalQuoteApiMock,
}))

function salesSession(
  factoryId = 'huaxing',
  includeBaselinePermissions = false,
  includeCustomerPermission = false,
): AuthMeResponse {
  const permissions = [
    'internal_quote:read',
    'internal_quote:create',
    'internal_quote:clone',
    ...(includeBaselinePermissions
      ? ['internal_quote:baseline_read', 'internal_quote:baseline_manage']
      : []),
    ...(includeCustomerPermission ? ['internal_quote:customer_manage'] : []),
  ]
  return {
    id: 'sales-user',
    username: 'sales-user',
    display_name: '华兴业务',
    roles: ['业务'],
    permissions,
    grants: [{
      role_id: 'position_sales_business',
      role_code: 'position_sales_business',
      role_name: '业务',
      factory_id: factoryId,
      department: 'sales-business',
      permissions,
      scope_mode: 'cross_factory_read',
      read_permission_codes: ['internal_quote:read'],
      unrestricted_department: true,
      data_scope: 'all',
    }],
    factory_scopes: ['*'],
    department_scopes: ['sales-business'],
    profile: {
      primary_factory_id: factoryId,
      primary_department: 'sales-business',
      position: '业务',
      confirmation_status: 'confirmed',
    },
    authz_mode: 'legacy',
    force_password_change: false,
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

function apiQuote(factoryId: string, id: string): ApiInternalQuote {
  return {
    id,
    factory_id: factoryId,
    workshop_code: `${factoryId}-workshop`,
    workshop_name: factoryId,
    quote_no: `IQ-${id}`,
    product_name: `${factoryId}产品`,
    customer: `${factoryId}客户`,
    qty: 100,
    version_label: 'V1',
    status: 'drafting',
    initiator_department: 'sales-business',
    business_owner_id: `${factoryId}-owner`,
    business_owner_name: `${factoryId}负责人`,
    target_date: '2026-08-01',
    remark: '',
    module_version: 'v2',
    reference_snapshot_id: 'ref-1',
    formula_version: 'v2',
    header_revision: 1,
    cloned_from_quote_id: '',
    archived_by: '',
    archived_at: '',
    archive_reason: '',
    final_release_status: '',
    final_submission_revision: 0,
    final_submission_manifest: {},
    final_submitted_by: '',
    final_submitted_by_name: '',
    final_submitted_at: '',
    final_reviewed_by: '',
    final_reviewed_by_name: '',
    final_reviewed_at: '',
    final_review_comment: '',
    final_release_revision: 0,
    final_release_invalidated_at: '',
    final_release_invalidation_reason: '',
    created_by: 'creator',
    created_by_name: '创建人',
    created_at: '2026-07-18 00:00:00',
    updated_at: '2026-07-18 00:00:00',
    sections: [],
  }
}

function pricingBaseline(factoryId: string, revision = 1): ApiInternalQuotePricingBaseline {
  return {
    factory_id: factoryId,
    workshop_code: `${factoryId}-workshop`,
    workshop_name: factoryId,
    revision,
    source_type: 'custom',
    updated_by: `${factoryId}-supervisor`,
    updated_by_name: `${factoryId}主管`,
    updated_at: '2026-07-20 10:00:00',
    material_prices: [{ material: `${factoryId}-ABS`, grade: '750SW', price_hkd_lb: '9.25' }],
    machine_prices: [{ machine_range: '4A-6A', machine: '80T', shift_price_hkd: '999' }],
  }
}

function apiCustomer(factoryId: string, name = `${factoryId}客户`, revision = 1): ApiInternalQuoteCustomer {
  return {
    id: `${factoryId}-customer`,
    factory_id: factoryId,
    name,
    revision,
    created_by: 'system',
    created_by_name: '系统迁移',
    created_at: '2026-07-21 10:00:00',
    updated_by: 'system',
    updated_by_name: '系统迁移',
    updated_at: '2026-07-21 10:00:00',
  }
}

const createPayload: InternalQuoteCreatePayload = {
  quoteNo: 'IQ-C-RACE',
  productName: 'C 厂竞态测试产品',
  customer: 'C 厂客户',
  versionLabel: 'V1',
  initiatorDepartment: 'sales-business' as const,
  businessOwnerId: 'huakang-c-owner',
  businessOwner: 'C 厂负责人',
  targetCustomerPrice: 'HKD 10',
  quantity: 100,
  targetDate: '2026-08-31',
  remark: '',
  participatingSections: ['sales', 'engineering', 'assembly'],
}

describe('InternalQuoteHome factory permission boundary', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    routerPushMock.mockReset()
    internalQuoteApiMock.list.mockReset().mockResolvedValue([])
    internalQuoteApiMock.listBusinessOwners.mockReset().mockResolvedValue([])
    internalQuoteApiMock.listCustomers.mockReset().mockImplementation((factoryId: string) => Promise.resolve([apiCustomer(factoryId)]))
    internalQuoteApiMock.createCustomer.mockReset()
    internalQuoteApiMock.updateCustomer.mockReset()
    internalQuoteApiMock.deleteCustomer.mockReset()
    internalQuoteApiMock.create.mockReset()
    internalQuoteApiMock.clone.mockReset()
    internalQuoteApiMock.getPricingBaseline.mockReset()
    internalQuoteApiMock.updatePricingBaseline.mockReset()
  })

  it('shows foreign factories as read-only and restores operations only in the home factory', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const authStore = useAuthStore()
    const appStore = useAppStore()
    authStore.applySession(salesSession())
    appStore.setActiveFactory('huadeng')

    const wrapper = mount(InternalQuoteHome, {
      global: { plugins: [pinia] },
    })

    await flushPromises()

    const createButton = wrapper.findAll('button').find((button) => (
      button.text().includes('新建内部报价')
    ))
    expect(createButton).toBeTruthy()
    expect(createButton!.attributes('disabled')).toBeDefined()
    expect(wrapper.get('.quote-readonly-notice').text()).toContain('华登 · 跨厂只读')
    expect(internalQuoteApiMock.list).toHaveBeenLastCalledWith('huadeng', { page: 1, pageSize: 10 })

    useAppStore().setActiveFactory('huaxing')
    await flushPromises()

    expect(wrapper.find('.quote-readonly-notice').exists()).toBe(false)
    expect(createButton!.attributes('disabled')).toBeUndefined()
    expect(internalQuoteApiMock.list).toHaveBeenLastCalledWith('huaxing', { page: 1, pageSize: 10 })

    useAppStore().setActiveFactory('huakang-c')
    await flushPromises()

    expect(wrapper.get('.quote-readonly-notice').text()).toContain('华康C · 跨厂只读')
    expect(internalQuoteApiMock.list).toHaveBeenLastCalledWith('huakang-c', { page: 1, pageSize: 10 })
  })

  it('shows customer maintenance only to the local sales supervisor and writes the active factory', async () => {
    const createdCustomer = apiCustomer('huaxing', '新增客户')
    internalQuoteApiMock.createCustomer.mockResolvedValue(createdCustomer)
    internalQuoteApiMock.updateCustomer.mockResolvedValue(apiCustomer('huaxing', '修改客户', 2))
    internalQuoteApiMock.deleteCustomer.mockResolvedValue(undefined)

    const pinia = createPinia()
    setActivePinia(pinia)
    useAuthStore().applySession(salesSession('huaxing', false, true))
    useAppStore().setActiveFactory('huaxing')
    const wrapper = mount(InternalQuoteHome, { global: { plugins: [pinia] } })
    await flushPromises()

    await wrapper.get('.quote-customer-button').trigger('click')
    const dialog = wrapper.findComponent(InternalQuoteCustomerDialog)
    expect(dialog.props('open')).toBe(true)

    dialog.vm.$emit('create', '新增客户')
    await flushPromises()
    expect(internalQuoteApiMock.createCustomer).toHaveBeenCalledWith('huaxing', '新增客户')

    dialog.vm.$emit('update', createdCustomer, '修改客户')
    await flushPromises()
    expect(internalQuoteApiMock.updateCustomer).toHaveBeenCalledWith(
      createdCustomer.id,
      '修改客户',
      createdCustomer.revision,
    )

    dialog.vm.$emit('delete', apiCustomer('huaxing', '修改客户', 2))
    await flushPromises()
    expect(internalQuoteApiMock.deleteCustomer).toHaveBeenCalledWith('huaxing-customer', 2)

    useAppStore().setActiveFactory('huadeng')
    await flushPromises()
    expect(wrapper.findComponent(InternalQuoteCustomerDialog).props('open')).toBe(false)
    expect(wrapper.find('.quote-customer-button').exists()).toBe(false)
  })

  it('ignores slow foreign responses and keeps create locked until home-factory owners are ready', async () => {
    const foreignQuotes = deferred<ApiInternalQuote[]>()
    const foreignOwners = deferred<Array<{ id: string; username: string; display_name: string }>>()
    const homeOwners = deferred<Array<{ id: string; username: string; display_name: string }>>()
    internalQuoteApiMock.list.mockImplementation((factoryId: string) => (
      factoryId === 'huadeng'
        ? foreignQuotes.promise
        : Promise.resolve([apiQuote('huaxing', 'HOME')])
    ))
    internalQuoteApiMock.listBusinessOwners.mockImplementation((factoryId: string) => (
      factoryId === 'huadeng' ? foreignOwners.promise : homeOwners.promise
    ))

    const pinia = createPinia()
    setActivePinia(pinia)
    useAuthStore().applySession(salesSession())
    useAppStore().setActiveFactory('huadeng')
    const wrapper = mount(InternalQuoteHome, { global: { plugins: [pinia] } })
    await flushPromises()

    useAppStore().setActiveFactory('huaxing')
    await flushPromises()
    const store = useInternalQuoteDeskStore()
    const createButton = wrapper.findAll('button').find((button) => button.text().includes('新建内部报价'))!
    expect(store.quotes.map((quote) => quote.id)).toEqual(['HOME'])
    expect(store.businessOwners).toEqual([])
    expect(createButton.attributes('disabled')).toBeDefined()

    homeOwners.resolve([{ id: 'home-owner', username: 'home', display_name: '本厂负责人' }])
    await flushPromises()
    expect(createButton.attributes('disabled')).toBeUndefined()
    expect(store.businessOwners.map((owner) => owner.id)).toEqual(['home-owner'])

    foreignQuotes.resolve([apiQuote('huadeng', 'FOREIGN')])
    foreignOwners.resolve([{ id: 'foreign-owner', username: 'foreign', display_name: '外厂负责人' }])
    await flushPromises()
    expect(store.currentFactoryId).toBe('huaxing')
    expect(store.quotes.map((quote) => quote.id)).toEqual(['HOME'])
    expect(store.businessOwners.map((owner) => owner.id)).toEqual(['home-owner'])
  })

  it('clears home-factory rows immediately when switching to a slow foreign factory', async () => {
    const foreignQuotes = deferred<ApiInternalQuote[]>()
    const foreignOwners = deferred<Array<{ id: string; username: string; display_name: string }>>()
    internalQuoteApiMock.list.mockImplementation((factoryId: string) => (
      factoryId === 'huaxing'
        ? Promise.resolve([apiQuote('huaxing', 'HOME')])
        : foreignQuotes.promise
    ))
    internalQuoteApiMock.listBusinessOwners.mockImplementation((factoryId: string) => (
      factoryId === 'huaxing'
        ? Promise.resolve([{ id: 'home-owner', username: 'home', display_name: '本厂负责人' }])
        : foreignOwners.promise
    ))

    const pinia = createPinia()
    setActivePinia(pinia)
    useAuthStore().applySession(salesSession())
    useAppStore().setActiveFactory('huaxing')
    const wrapper = mount(InternalQuoteHome, { global: { plugins: [pinia] } })
    await flushPromises()
    expect(useInternalQuoteDeskStore().quotes.map((quote) => quote.id)).toEqual(['HOME'])

    useAppStore().setActiveFactory('huakang-d')
    await wrapper.vm.$nextTick()
    expect(useInternalQuoteDeskStore().quotes).toEqual([])
    expect(wrapper.find('.quote-readonly-notice').text()).toContain('华康D · 跨厂只读')
    expect(wrapper.find('.quote-number').exists()).toBe(false)

    foreignQuotes.resolve([])
    foreignOwners.resolve([])
    await flushPromises()
  })

  it.each([
    ['huakang-c', 'C-QUOTE'],
    ['huakang-d', 'D-QUOTE'],
  ] as const)('keeps %s in quote detail navigation', async (factoryId, quoteId) => {
    internalQuoteApiMock.list.mockImplementation((factoryId: string) =>
      Promise.resolve([apiQuote(factoryId, quoteId)]),
    )
    internalQuoteApiMock.listBusinessOwners.mockResolvedValue([])

    const pinia = createPinia()
    setActivePinia(pinia)
    useAuthStore().applySession(salesSession())
    useAppStore().setActiveFactory(factoryId)
    const wrapper = mount(InternalQuoteHome, { global: { plugins: [pinia] } })
    await flushPromises()

    await wrapper.get('.quote-number').trigger('click')

    expect(routerPushMock).toHaveBeenCalledWith(
      `/modules/sales-business/internal-quote-desk/${quoteId}/collaboration?factory=${factoryId}`,
    )
  })

  it('uses the factory returned by a successful create when opening collaboration', async () => {
    internalQuoteApiMock.list.mockResolvedValue([])
    internalQuoteApiMock.listBusinessOwners.mockResolvedValue([
      { id: 'huakang-c-owner', username: 'c-owner', display_name: 'C 厂负责人' },
    ])
    internalQuoteApiMock.create.mockResolvedValue(apiQuote('huakang-c', 'C-CREATED'))

    const pinia = createPinia()
    setActivePinia(pinia)
    useAuthStore().applySession(salesSession('huakang-c'))
    useAppStore().setActiveFactory('huakang-c')
    const wrapper = mount(InternalQuoteHome, { global: { plugins: [pinia] } })
    await flushPromises()

    await wrapper.get('.quote-new-button').trigger('click')
    wrapper.findComponent(InternalQuoteCreateDialog).vm.$emit('confirm', createPayload)
    await flushPromises()

    expect(routerPushMock).toHaveBeenCalledWith(
      '/modules/sales-business/internal-quote-desk/C-CREATED/collaboration?factory=huakang-c',
    )
    expect(useInternalQuoteDeskStore().quotes.map((quote) => quote.id)).toEqual(['C-CREATED'])
  })

  it.each(['create', 'clone'] as const)(
    'drops a stale C-factory %s response after a C to D to C switch',
    async (mode) => {
      const operation = deferred<ApiInternalQuote>()
      internalQuoteApiMock.list.mockImplementation((factoryId: string) => Promise.resolve(
        factoryId === 'huakang-c' ? [apiQuote('huakang-c', 'C-SOURCE')] : [],
      ))
      internalQuoteApiMock.listBusinessOwners.mockImplementation((factoryId: string) => Promise.resolve(
        factoryId === 'huakang-c'
          ? [{ id: 'huakang-c-owner', username: 'c-owner', display_name: 'C 厂负责人' }]
          : [],
      ))
      internalQuoteApiMock.create.mockReturnValue(operation.promise)
      internalQuoteApiMock.clone.mockReturnValue(operation.promise)

      const pinia = createPinia()
      setActivePinia(pinia)
      useAuthStore().applySession(salesSession('huakang-c'))
      const appStore = useAppStore()
      appStore.setActiveFactory('huakang-c')
      const wrapper = mount(InternalQuoteHome, { global: { plugins: [pinia] } })
      await flushPromises()

      if (mode === 'create') {
        await wrapper.get('.quote-new-button').trigger('click')
      }
      else {
        await wrapper.get('button[aria-label="复制报价"]').trigger('click')
      }
      wrapper.findComponent(InternalQuoteCreateDialog).vm.$emit('confirm', createPayload)
      await Promise.resolve()
      expect(mode === 'create' ? internalQuoteApiMock.create : internalQuoteApiMock.clone).toHaveBeenCalledTimes(1)

      appStore.setActiveFactory('huakang-d')
      await flushPromises()
      appStore.setActiveFactory('huakang-c')
      await flushPromises()

      operation.resolve(apiQuote('huakang-c', mode === 'create' ? 'C-CREATED' : 'C-CLONED'))
      await flushPromises()

      expect(routerPushMock).not.toHaveBeenCalled()
      expect(useInternalQuoteDeskStore().quotes.map((quote) => quote.id)).toEqual(['C-SOURCE'])
      expect(wrapper.findComponent(InternalQuoteCreateDialog).props('open')).toBe(false)
    },
  )

  it('closes and clears a baseline dialog and ignores its stale ABA load response', async () => {
    const staleBaseline = deferred<ApiInternalQuotePricingBaseline>()
    internalQuoteApiMock.getPricingBaseline.mockReturnValue(staleBaseline.promise)
    internalQuoteApiMock.listBusinessOwners.mockResolvedValue([
      { id: 'huakang-c-owner', username: 'c-owner', display_name: 'C 厂负责人' },
    ])

    const pinia = createPinia()
    setActivePinia(pinia)
    useAuthStore().applySession(salesSession('huakang-c', true))
    const appStore = useAppStore()
    appStore.setActiveFactory('huakang-c')
    const wrapper = mount(InternalQuoteHome, { global: { plugins: [pinia] } })
    await flushPromises()

    await wrapper.get('.quote-baseline-button').trigger('click')
    expect(wrapper.findComponent(InternalQuoteBaselineDialog).props('open')).toBe(true)

    appStore.setActiveFactory('huakang-d')
    await wrapper.vm.$nextTick()
    expect(wrapper.findComponent(InternalQuoteBaselineDialog).props('open')).toBe(false)
    wrapper.findComponent(InternalQuoteBaselineDialog).vm.$emit('save', {
      revision: 1,
      workshop_name: '华康C',
      material_prices: [],
      machine_prices: [],
    })
    await flushPromises()
    expect(internalQuoteApiMock.updatePricingBaseline).not.toHaveBeenCalled()

    appStore.setActiveFactory('huakang-c')
    await flushPromises()
    staleBaseline.resolve(pricingBaseline('huakang-c'))
    await flushPromises()

    const store = useInternalQuoteDeskStore()
    expect(store.pricingBaseline).toBeNull()
    expect(store.pricingBaselineFactoryId).toBe('')
    expect(wrapper.findComponent(InternalQuoteBaselineDialog).props('open')).toBe(false)
  })

  it('does not apply a stale baseline update after switching C to D to C', async () => {
    const staleUpdate = deferred<ApiInternalQuotePricingBaseline>()
    internalQuoteApiMock.getPricingBaseline.mockResolvedValue(pricingBaseline('huakang-c'))
    internalQuoteApiMock.updatePricingBaseline.mockReturnValue(staleUpdate.promise)

    const pinia = createPinia()
    setActivePinia(pinia)
    useAuthStore().applySession(salesSession('huakang-c', true))
    const appStore = useAppStore()
    appStore.setActiveFactory('huakang-c')
    const wrapper = mount(InternalQuoteHome, { global: { plugins: [pinia] } })
    await flushPromises()

    await wrapper.get('.quote-baseline-button').trigger('click')
    await flushPromises()
    wrapper.findComponent(InternalQuoteBaselineDialog).vm.$emit('save', {
      revision: 1,
      workshop_name: '华康C',
      material_prices: [{ material: 'C-ABS', grade: '750SW', price_hkd_lb: '10.00' }],
      machine_prices: [{ machine_range: '4A-6A', machine: '80T', shift_price_hkd: '1000' }],
    })
    await Promise.resolve()
    expect(internalQuoteApiMock.updatePricingBaseline).toHaveBeenCalledWith(
      'huakang-c',
      'huakang-c-workshop',
      expect.any(Object),
    )

    appStore.setActiveFactory('huakang-d')
    await flushPromises()
    appStore.setActiveFactory('huakang-c')
    await flushPromises()
    staleUpdate.resolve(pricingBaseline('huakang-c', 2))
    await flushPromises()

    expect(useInternalQuoteDeskStore().pricingBaseline).toBeNull()
    expect(wrapper.findComponent(InternalQuoteBaselineDialog).props('open')).toBe(false)
  })
})
