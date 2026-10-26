import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, onBeforeUnmount, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import InternalQuoteDeskView from '@/views/InternalQuoteDeskView.vue'
import { clearQuoteNavigationGuards, guardQuoteNavigation, registerQuoteNavigationGuard } from '../navigationGuard'

const wrappers: Array<ReturnType<typeof mount>> = []
const Child = defineComponent({ setup() {
  const draft = ref('私有草稿')
  onBeforeUnmount(registerQuoteNavigationGuard(() => draft.value !== '阻止离开'))
  return () => h('input', { 'aria-label': '报价草稿', value: draft.value, onInput: (e: Event) => { draft.value = (e.target as HTMLInputElement).value } })
} })
async function setup(financial = true) {
  const pinia = createPinia(), auth = useAuthStore(pinia), store = useInternalQuoteDeskStore(pinia)
  auth.currentUser = { id: 'actor-1', identity: { employment_epoch: '1' } } as never
  vi.spyOn(auth, 'can').mockImplementation(permission => permission === 'internal_quote:summary_read' ? financial : true)
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/quotes', component: InternalQuoteDeskView, children: [
    { path: '', name: 'internal-quote-desk-home', component: { template: '<h1>报价首页</h1>' } },
    { path: ':quoteId/collaboration', name: 'internal-quote-collaboration', component: Child },
  ] }] })
  router.beforeEach(guardQuoteNavigation)
  await router.push('/quotes/q1/collaboration?factory=huakang-a')
  const wrapper = mount({ template: '<RouterView />' }, { global: { plugins: [pinia, router], stubs: {
    SalesModuleWorkbench: { template: '<main><slot /></main>' },
    QuoteRecordReadOnly: { props: ['quoteId', 'factoryId'], template: '<div data-readonly>{{ factoryId }} / {{ quoteId }}</div>' },
  } } })
  wrappers.push(wrapper); await flushPromises()
  return { wrapper, router, auth, store }
}
beforeEach(() => { clearQuoteNavigationGuards(); vi.spyOn(window, 'scrollTo').mockImplementation(() => {}) })
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()); clearQuoteNavigationGuards(); vi.restoreAllMocks() })

describe('native quote workspace identity boundary', () => {
  it('uses the native operational-only surface when summary permission is absent', async () => {
    const { wrapper } = await setup(false)
    expect(wrapper.get('[data-readonly]').text()).toBe('huakang-a / q1')
    expect(wrapper.find('input').exists()).toBe(false)
  })

  it('clears private state and old guards on authorization changes and never restores the old record automatically', async () => {
    const { wrapper, router, auth, store } = await setup()
    await wrapper.get('input').setValue('阻止离开')
    store.quotes = [{ ...store.placeholderQuote, id: 'q1', productName: '旧账号私有产品' }]
    store.versionCandidates = { q1: [] }
    auth.authorizationVersion++
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('internal-quote-desk-home')
    expect(store.quotes).toEqual([])
    expect(store.versionCandidates).toEqual({})
    expect(wrapper.find('input').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('旧账号私有产品')
  })

  it('keeps an explicit new record link across factories but clears the old record on factory-only navigation', async () => {
    const { router, store, wrapper } = await setup()
    await router.push('/quotes/q2/collaboration?factory=huakang-b'); await flushPromises()
    expect(router.currentRoute.value.params.quoteId).toBe('q2')
    expect(store.factoryContextFactoryId).toBe('huakang-b')
    expect(wrapper.get('input').element.value).toBe('私有草稿')
    await wrapper.get('input').setValue('阻止离开')
    await router.push('/quotes/q2/collaboration?factory=huakang-a'); await flushPromises()
    expect(store.factoryContextFactoryId).toBe('huakang-b')
    await wrapper.get('input').setValue('允许离开')
    await router.push('/quotes/q2/collaboration?factory=huakang-a'); await flushPromises()
    expect(router.currentRoute.value.name).toBe('internal-quote-desk-home')
    expect(store.factoryContextFactoryId).toBe('huakang-a')
  })
})
