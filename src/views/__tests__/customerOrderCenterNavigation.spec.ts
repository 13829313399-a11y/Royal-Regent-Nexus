import { flushPromises, mount } from '@vue/test-utils'
import { reactive } from 'vue'
import { beforeEach, expect, it, vi } from 'vitest'
import CustomerOrderCenterView from '@/views/CustomerOrderCenterView.vue'

const state = vi.hoisted(() => ({
  store: null as unknown as { activeProductionFactory: { id: string; shortName: string }; setActiveDepartment: ReturnType<typeof vi.fn> },
  route: null as unknown as { query: Record<string, string | undefined> },
  replace: vi.fn(),
}))
vi.mock('@/stores/app', () => ({ useAppStore: () => state.store }))
vi.mock('vue-router', () => ({
  RouterLink: { props: ['to'], template: '<a><slot /></a>' },
  useRoute: () => state.route,
  useRouter: () => ({ replace: state.replace }),
}))
vi.mock('@/components/layout/AccountMenu.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/common/UsageGuideDialog.vue', () => ({ default: { template: '<div><slot name="trigger" /></div>' } }))
vi.mock('@/features/cutting-operations/CuttingAcceptanceNotice.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/features/module-feedback/ModuleFeedbackHub.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/CartonQuickAssetLibrary.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/modules/sales/customer-order-center/HuakangBJPIntake.vue', () => ({
  default: { props: ['factoryId'], template: '<div data-testid="jp-workspace">JP问单 {{ factoryId }}</div>' },
}))
vi.mock('@/components/modules/sales/customer-order-center/CustomerOrderCenterWorkspace.vue', () => ({
  default: { name: 'CustomerOrderCenterWorkspace', props: ['activeSection', 'factoryId', 'focusLineId'], emits: ['navigate'],
    template: '<div data-testid="formal-workspace">{{ factoryId }} {{ activeSection }} {{ focusLineId }}</div>' },
}))

beforeEach(() => {
  state.store = reactive({ activeProductionFactory: { id: 'huakang-b', shortName: '华康B' }, setActiveDepartment: vi.fn() })
  state.route = reactive({ query: {} })
  state.replace.mockReset()
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
})

it('opens B directly on enquiry intake and removes the unrelated PO and preview entry points', async () => {
  const wrapper = mount(CustomerOrderCenterView)
  await flushPromises()
  expect(wrapper.get('[data-testid="jp-workspace"]').text()).toContain('huakang-b')
  expect(wrapper.find('[data-testid="formal-workspace"]').exists()).toBe(false)
  expect(wrapper.get('.order-new-button').text()).toBe('新建问单')
  for (const selector of ['.order-sidebar__nav', '.order-mobile-nav']) {
    const navigation = wrapper.get(selector).text()
    expect(navigation).toContain('JP问单录入')
    expect(navigation).not.toContain('PO 与排期导入')
    expect(navigation).not.toContain('预览与确认')
    expect(navigation).not.toContain('工作台')
    expect(navigation).toContain('订单数据台账')
  }
  expect(wrapper.get('.order-sidebar__scope').text()).toContain('导入邮件并核对问单明细')
  await wrapper.get('.order-new-button').trigger('click')
  expect(wrapper.find('[data-testid="formal-workspace"]').exists()).toBe(false)
  wrapper.unmount()
})

it('normalizes factory switches while preserving ordinary PO navigation in other factories', async () => {
  state.store.activeProductionFactory = { id: 'huaxing', shortName: '华兴' }
  const wrapper = mount(CustomerOrderCenterView)
  await wrapper.get('.order-new-button').trigger('click')
  expect(wrapper.get('[data-testid="formal-workspace"]').text()).toContain('huaxing import')
  const previousWorkspace = wrapper.findComponent({ name: 'CustomerOrderCenterWorkspace' })
  state.store.activeProductionFactory = { id: 'huakang-b', shortName: '华康B' }
  // A same-tick event from the old workspace cannot reopen B's PO intake.
  previousWorkspace.vm.$emit('navigate', 'import')
  await flushPromises()
  expect(wrapper.get('[data-testid="jp-workspace"]').text()).toContain('huakang-b')
  expect(wrapper.find('[data-testid="formal-workspace"]').exists()).toBe(false)
  state.store.activeProductionFactory = { id: 'huakang-a', shortName: '华康A' }
  await flushPromises()
  expect(wrapper.get('[data-testid="formal-workspace"]').text()).toContain('huakang-a ledger')
  expect(wrapper.find('[data-testid="jp-workspace"]').exists()).toBe(false)
  expect(wrapper.get('.order-sidebar__nav').text()).toContain('PO 与排期导入')
  await wrapper.get('.order-new-button').trigger('click')
  expect(wrapper.get('[data-testid="formal-workspace"]').text()).toContain('huakang-a import')
  wrapper.unmount()
})

it('routes old B import bookmarks and requests from historical ledger back to JP intake', async () => {
  state.route.query = { factory: 'huakang-b', section: 'import' }
  const wrapper = mount(CustomerOrderCenterView)
  await flushPromises()
  expect(wrapper.find('[data-testid="jp-workspace"]').exists()).toBe(true)
  const ledgerButton = wrapper.get('.order-sidebar__nav').findAll('button').find(button => button.text() === '订单数据台账')!
  await ledgerButton.trigger('click')
  expect(wrapper.get('[data-testid="formal-workspace"]').text()).toContain('huakang-b ledger')
  wrapper.findComponent({ name: 'CustomerOrderCenterWorkspace' }).vm.$emit('navigate', 'preview')
  await flushPromises()
  expect(wrapper.find('[data-testid="jp-workspace"]').exists()).toBe(true)
  await ledgerButton.trigger('click')
  state.route.query.section = 'preview'
  await flushPromises()
  expect(wrapper.find('[data-testid="jp-workspace"]').exists()).toBe(true)
  wrapper.unmount()
})

it('preserves explicit historical-order links without enabling B PO intake', async () => {
  state.route.query = { factory: 'huakang-b', order: 'historical-order-id' }
  const wrapper = mount(CustomerOrderCenterView)
  await flushPromises()
  expect(wrapper.get('[data-testid="formal-workspace"]').text()).toContain('huakang-b ledger historical-order-id')
  expect(wrapper.get('.order-sidebar__nav').text()).not.toContain('PO 与排期导入')
  await wrapper.get('.order-new-button').trigger('click')
  expect(state.replace).toHaveBeenCalledWith({ query: { factory: 'huakang-b', order: undefined } })
  expect(wrapper.find('[data-testid="jp-workspace"]').exists()).toBe(true)
  wrapper.unmount()
})
