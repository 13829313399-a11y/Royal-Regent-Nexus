import { flushPromises, shallowMount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import InternalQuoteCollaboration from '../InternalQuoteCollaboration.vue'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { quoteId: 'quote-1' }, query: {} }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

function setup(userId = 'creator', status = 'final_pending') {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.applySession({
    id: userId, username: userId, display_name: userId, roles: ['业务'],
    permissions: ['internal_quote:create', 'internal_quote:read'],
    factory_scopes: ['huaxing'], department_scopes: ['sales-business'],
    grants: [{ role_id: 'sales_customer_owner', role_name: '业务', factory_id: 'huaxing', department: 'sales-business',
      permissions: ['internal_quote:create', 'internal_quote:read'], data_scope: 'department' }],
    force_password_change: false,
  })
  const app = useAppStore()
  vi.spyOn(app, 'activeFactory', 'get').mockReturnValue({ id: 'huaxing' } as typeof app.activeFactory)
  const store = useInternalQuoteDeskStore()
  const quote = { ...store.placeholderQuote, id: 'quote-1', quoteNo: 'IQ-1', productName: '测试产品',
    factoryId: 'huaxing', moduleVersion: 'v3', status, createdById: 'creator', businessOwnerId: 'reviewer',
    businessOwner: '业务审核人', headerRevision: 2 } as typeof store.placeholderQuote
  store.quotes = [quote]
  vi.spyOn(store, 'loadQuote').mockResolvedValue(quote)
  vi.spyOn(store, 'loadBatchProducts').mockResolvedValue(undefined)
  const withdraw = vi.spyOn(store, 'withdrawFinal').mockResolvedValue(undefined)
  const wrapper = shallowMount(InternalQuoteCollaboration, { global: { plugins: [pinia], stubs: { RouterLink: true } } })
  return { wrapper, store, withdraw }
}

beforeEach(() => {
  vi.stubGlobal('IntersectionObserver', class { observe() {} disconnect() {} })
})
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('creator withdrawal interaction', () => {
  it('requires confirmation and a reason before calling the withdrawal action', async () => {
    const { wrapper, store, withdraw } = setup()
    await flushPromises()
    const button = wrapper.findAll('button').find((item) => item.text() === '退回修改')!
    expect(button.exists()).toBe(true)
    await button.trigger('click')
    const panel = wrapper.get('[aria-label="建单人退回修改"]')
    const confirm = panel.findAll('button').find((item) => item.text() === '确认退回修改')!
    expect(confirm.attributes('disabled')).toBeDefined()
    expect(withdraw).not.toHaveBeenCalled()
    await panel.get('textarea').setValue('  客户数量改变  ')
    await confirm.trigger('click')
    await flushPromises()
    expect(withdraw).toHaveBeenCalledWith('quote-1', 2, '客户数量改变')
    expect(store.loadBatchProducts).toHaveBeenCalledWith('quote-1')
    expect(wrapper.find('[aria-label="建单人退回修改"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('报价已退回修改')
    wrapper.unmount()
  })

  it.each([['other', 'final_pending'], ['creator', 'released'], ['creator', 'exported']])('hides withdrawal for %s in %s', async (userId, status) => {
    const { wrapper } = setup(userId, status)
    await flushPromises()
    expect(wrapper.findAll('button').some((item) => item.text() === '退回修改')).toBe(false)
    wrapper.unmount()
  })

  it('keeps the reason and displays a server conflict without reporting success', async () => {
    const { wrapper, withdraw } = setup()
    withdraw.mockRejectedValue(new Error('报价已审核，请刷新'))
    await flushPromises()
    await wrapper.findAll('button').find((item) => item.text() === '退回修改')!.trigger('click')
    await wrapper.get('[aria-label="退回修改原因"]').setValue('调整数量')
    await wrapper.findAll('button').find((item) => item.text() === '确认退回修改')!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('报价已审核，请刷新')
    expect(wrapper.text()).not.toContain('报价已退回修改，整批内容已解锁')
    expect((wrapper.get('textarea[aria-label="退回修改原因"]').element as HTMLTextAreaElement).value).toBe('调整数量')
    wrapper.unmount()
  })
})
