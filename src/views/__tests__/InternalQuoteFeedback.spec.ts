import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import InternalQuoteDeskView from '../InternalQuoteDeskView.vue'

const mocks = vi.hoisted(() => ({
  reset: vi.fn(), activate: vi.fn(), openComposer: vi.fn(),
  route: { name: 'internal-quote-collaboration', fullPath: '/internal-quote/q1', params: { quoteId: 'q1' }, query: { factory: 'huaxing' } },
}))
vi.mock('vue-router', () => ({
  useRoute: () => mocks.route,
  useRouter: () => ({ replace: vi.fn() }),
  RouterView: { setup: () => ({ route: mocks.route }), template: '<slot :Component="\'QuoteEditor\'" :route="route" />' },
}))
vi.mock('@/stores/app', () => ({ useAppStore: () => ({ activeFactory: { id: 'huaxing', shortName: '华兴' }, activeProductionFactory: { id: 'huaxing' }, setActiveDepartment: vi.fn() }) }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ currentUser: { id: 'reporter' }, can: () => true }) }))
vi.mock('@/stores/internalQuoteDesk', () => ({ useInternalQuoteDeskStore: () => ({ resetPrivateContext: mocks.reset, activateFactoryContext: mocks.activate }) }))
vi.mock('@/features/internal-quote/assistantContext', () => ({ quoteDepartments: ['sales-business'] }))
vi.mock('@/features/internal-quote/QuoteRecordReadOnly.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/modules/sales/SalesModuleWorkbench.vue', () => ({ default: { template: '<main><slot /></main>' } }))
vi.mock('@/features/module-feedback/ModuleFeedbackHub.vue', () => ({ default: defineComponent({
  props: ['module', 'factoryId', 'factoryName', 'active'], emits: ['navigate', 'unread'],
  setup(props, { expose }) { expose({ openComposer: mocks.openComposer }); return () => h('div', { 'data-feedback-active': String(props.active), 'data-module': props.module }) },
}) }))

describe('internal quote feedback entry', () => {
  it('preserves an unsaved quote when opening feedback and captures the active quote', async () => {
    const QuoteEditor = defineComponent({ setup() {
      const draft = ref('')
      return () => h('input', { 'aria-label': '报价草稿', value: draft.value, onInput: (event: Event) => { draft.value = (event.target as HTMLInputElement).value } })
    } })
    const wrapper = mount(InternalQuoteDeskView, { global: { components: { QuoteEditor } } })
    try {
      await wrapper.get('input').setValue('尚未保存的报价')
      const resets = mocks.reset.mock.calls.length
      await wrapper.findAll('button').find(item => item.text() === '反馈问题')!.trigger('click')
      expect(mocks.openComposer).toHaveBeenCalledWith(expect.objectContaining({ quote_id: 'q1', page: '内部报价台' }))
      await wrapper.findAll('button').find(item => item.text() === '反馈与答复')!.trigger('click')
      await flushPromises()
      expect(wrapper.get('[data-feedback-active]').attributes('data-feedback-active')).toBe('true')
      expect(wrapper.get('[data-module]').attributes('data-module')).toBe('internal-quote')
      await wrapper.findAll('button').find(item => item.text() === '返回报价')!.trigger('click')
      expect((wrapper.get('input').element as HTMLInputElement).value).toBe('尚未保存的报价')
      expect(mocks.reset).toHaveBeenCalledTimes(resets)
    } finally { wrapper.unmount() }
  })
})
