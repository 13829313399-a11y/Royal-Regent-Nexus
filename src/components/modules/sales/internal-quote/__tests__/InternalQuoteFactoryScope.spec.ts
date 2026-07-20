import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AuthMeResponse } from '@/api/auth'
import type { ApiInternalQuote } from '@/api/internalQuote'
import InternalQuoteHome from '@/components/modules/sales/internal-quote/InternalQuoteHome.vue'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'

const routerPushMock = vi.hoisted(() => vi.fn())
const internalQuoteApiMock = vi.hoisted(() => ({
  list: vi.fn(),
  listBusinessOwners: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPushMock }),
}))

vi.mock('@/api/internalQuote', () => ({
  internalQuoteApi: internalQuoteApiMock,
}))

function salesSession(): AuthMeResponse {
  const permissions = [
    'internal_quote:read',
    'internal_quote:create',
    'internal_quote:clone',
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
      factory_id: 'huaxing',
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
      primary_factory_id: 'huaxing',
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

describe('InternalQuoteHome factory permission boundary', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    routerPushMock.mockReset()
    internalQuoteApiMock.list.mockReset().mockResolvedValue([])
    internalQuoteApiMock.listBusinessOwners.mockReset().mockResolvedValue([])
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
})
