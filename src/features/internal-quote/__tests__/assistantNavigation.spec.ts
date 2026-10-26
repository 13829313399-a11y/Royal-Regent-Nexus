import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, reactive, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { readFileSync } from 'node:fs'
import { quoteSelection } from '../assistantContext'
import { clearQuoteNavigationGuards, guardQuoteNavigation, registerQuoteNavigationGuard } from '../navigationGuard'
import { useQuoteOperationScope } from '../operationScope'
import { registerAssistantSelection } from '@/features/assistant/selection'
import { useDraftScope } from '@/features/assistant/draftScope'
import type { Draft, PageContext } from '@/features/assistant/types'

afterEach(clearQuoteNavigationGuards)

describe('native quote scope and early navigation', () => {
  it('freezes the exact native filters and ordered comparison without following later UI changes', () => {
    const ids = ref(['base', 'target'])
    const filters = reactive({ keyword: '原报价', customer: '客户 A', status: 'drafting', view: 'compare' })
    const page = ref<PageContext>({ module_id: 'internal-quote', route_name: 'internal-quote-summary', factory_id: 'huaxing' })
    const unregister = registerAssistantSelection('internal-quote', () => quoteSelection(page.value.factory_id!, ids.value, filters))
    const draft = reactive<Draft>({ text: '', attachments: [], documents: [] })
    try {
      const scope = useDraftScope(() => draft, () => page.value, () => '内部报价')
      scope.freeze()
      ids.value = ['other']; filters.keyword = '新条件'; filters.status = 'exported'
      page.value = { ...page.value, factory_id: 'huakang-b' }
      expect(scope.scope.value.selection?.resources.map(r => r.resource_id)).toEqual(['base', 'target'])
      expect(scope.scope.value.selection?.filters).toEqual({ keyword: '原报价', customer: '客户 A', status: 'drafting', view: 'compare', factory_id: 'huaxing' })
      expect(scope.changed.value).toBe(true)
      scope.adopt()
      expect(scope.scope.value.selection?.resources.map(r => r.resource_id)).toEqual(['other'])
      expect(scope.scope.value.selection?.filters.factory_id).toBe('huakang-b')
    } finally { unregister() }
  })

  it('rejects ambiguous factory, duplicate, oversized and unverified selections instead of broadening', () => {
    for (const selection of [quoteSelection('group', ['q1']), quoteSelection('huaxing', ['q1', 'q1']),
      quoteSelection('huaxing', [' q1']), quoteSelection('huaxing', Array.from({ length: 11 }, (_, i) => String(i))),
      quoteSelection('huaxing', [], { keyword: '字'.repeat(129) }), quoteSelection('huaxing', ['q1'], { scope_error: '尚未读取成功' })]) {
      expect(selection.resources).toEqual([])
      expect(selection.filters.scope_error).toBeTruthy()
    }
    expect(quoteSelection('huaxing', [], { factory_id: 'huakang-b', keyword: '', status: '' }).filters)
      .toEqual({ factory_id: 'huaxing', keyword: '', status: '' })
  })

  it('waits for the native draft decision before mutating factory context, including same-route query changes', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/quote/:id', name: 'quote', component: { template: '<div />' } }, { path: '/login', name: 'login', component: { template: '<div />' } }] })
    let factory = 'huaxing'
    router.beforeEach(async (to, from) => {
      if (!await guardQuoteNavigation(to, from)) return false
      factory = String(to.query.factory ?? '')
    })
    await router.push('/quote/q1?factory=huaxing')
    let decide!: (allow: boolean) => void
    const check = vi.fn(() => new Promise<boolean>(resolve => { decide = resolve }))
    const unregister = registerQuoteNavigationGuard(check)
    const cancelled = router.push('/quote/q1?factory=huakang-b')
    await flushPromises()
    expect(factory).toBe('huaxing')
    decide(false); await cancelled
    expect(router.currentRoute.value.query.factory).toBe('huaxing')
    const accepted = router.push('/quote/q2?factory=huakang-b')
    await flushPromises(); expect(factory).toBe('huaxing')
    decide(true); await accepted
    expect(factory).toBe('huakang-b')
    unregister()
    registerQuoteNavigationGuard(() => false)
    await router.push('/login')
    expect(router.currentRoute.value.name).toBe('login')
    const source = readFileSync('src/router/index.ts', 'utf8')
    expect(source.indexOf('await guardQuoteNavigation(to, from)')).toBeLessThan(source.indexOf('appStore.setRequestedFactoryContext(factoryQuery.factory)'))
  })

  it('invalidates multi-step operations synchronously on record change and on unmount', async () => {
    const id = ref('q1')
    let capture!: () => () => void
    const wrapper = mount(defineComponent({ setup() { capture = useQuoteOperationScope(() => id.value); return () => null } }))
    const old = capture()
    id.value = 'q2'
    expect(old).toThrow('报价上下文已变化')
    const current = capture(); expect(current).not.toThrow()
    wrapper.unmount()
    expect(current).toThrow('报价上下文已变化')
  })
})
