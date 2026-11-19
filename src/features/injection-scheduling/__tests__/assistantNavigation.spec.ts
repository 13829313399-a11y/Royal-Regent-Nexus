// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, reactive } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory, RouterView } from 'vue-router'
import { injectionApi } from '@/api/injectionScheduling'
import { useInjectionStore } from '@/stores/injectionScheduling'
import { assistantSelection } from '@/features/assistant/selection'
import { guardInjectionNavigation } from '../navigationGuard'
import InjectionSchedulingView from '@/views/InjectionSchedulingView.vue'

const auth = reactive({ currentUser: { id: 'synthetic-a' }, can: (permission: string) => permission === 'injection_scheduling:read' })
const app = reactive({ activeFactoryId: 'huakang-a', setActiveFactory(id: string) { this.activeFactoryId = id } })
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))
vi.mock('@/stores/app', () => ({ useAppStore: () => app }))
vi.mock('@/api/injectionScheduling', () => ({ injectionApi: { get: vi.fn(), query: vi.fn(), post: vi.fn(), patch: vi.fn() } }))
const api = vi.mocked(injectionApi)
const wrappers: ReturnType<typeof mount>[] = []
function detail(id: string) { return { demand: { id, mold_code: id, order_no: '合成需求', remaining_shots: 10 }, run: null, history: [], reports: [], source_rows: [] } }
beforeEach(() => {
  setActivePinia(createPinia())
  vi.resetAllMocks()
  auth.currentUser = { id: 'synthetic-a' }
  auth.can = (permission: string) => permission === 'injection_scheduling:read'
  app.activeFactoryId = 'huakang-a'
  api.get.mockImplementation(async (path) => {
    if (path === '/field-registry') return { fields: [{ key: 'mold_code', label: '模号', value_type: 'text', group: 'identity', filter_ops: ['eq'], editable: true }] }
    if (path === '/settings') return { parameters: {} }
    if (path === '/views') return []
    if (path === '/summary') return { revision: 1, shared_revision: 1 }
    if (path === '/timeline') return { revision: 1, machines: [], runs: [], events: [] }
    if (path.startsWith('/demands/')) return detail(path.split('/').at(-1)!)
    return { revision: 1, shared_revision: 1 }
  })
  api.query.mockResolvedValue({ rows: [], total_count: 0, filtered_summary: {}, revision: 1, shared_revision: 1, next_cursor: null })
})
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()); document.body.innerHTML = ''; vi.unstubAllGlobals() })
async function open(url = '/injection?factory=huakang-a&demand=SYN-A1') {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/injection', name: 'injection-scheduling', component: InjectionSchedulingView },
    { path: '/elsewhere', component: { template: '<p>其他模块</p>' } },
  ] })
  // Same ordering as the application router: guard first, factory mutation second.
  router.beforeEach((to, from) => {
    if (!guardInjectionNavigation(to, from)) return false
    if (typeof to.query.factory === 'string') app.setActiveFactory(to.query.factory)
  })
  await router.push(url)
  const wrapper = mount(defineComponent({ components: { RouterView }, template: '<RouterView />' }), {
    attachTo: document.body, global: { plugins: [router], stubs: { ScheduleBoard: true, PlanTable: true, ShiftReports: true, MasterData: true } },
  })
  wrappers.push(wrapper)
  await flushPromises()
  return { wrapper, router, store: useInjectionStore() }
}

it('opens the factory-bound native demand after factory load, then Escape clears the URL and restores focus', async () => {
  const trigger = document.createElement('button'); trigger.textContent = '原需求入口'; document.body.append(trigger); trigger.focus()
  const { wrapper, router, store } = await open()
  expect(api.get).toHaveBeenCalledWith('/demands/SYN-A1', { factory_id: 'huakang-a' })
  expect(wrapper.get('[aria-label="需求详情"]').text()).toContain('SYN-A1')
  expect(store.selectedId).toBe('SYN-A1')
  await wrapper.get('[aria-label="需求详情"]').trigger('keydown', { key: 'Escape' }); await flushPromises()
  expect(router.currentRoute.value.query.demand).toBeUndefined()
  expect(wrapper.find('[aria-label="需求详情"]').exists()).toBe(false)
  expect(document.activeElement).toBe(trigger)
})

it('protects a draft and pending write before route/factory mutation, without replaying a blocked intent', async () => {
  const { router, store } = await open()
  for (const state of ['dirty', 'busy'] as const) {
    store[state] = true
    await router.push('/injection?factory=huakang-b&demand=SYN-B1'); await flushPromises()
    expect(router.currentRoute.value.query.factory).toBe('huakang-a')
    expect(app.activeFactoryId).toBe('huakang-a')
    expect(store.selectedId).toBe('SYN-A1')
    expect(api.get).not.toHaveBeenCalledWith('/demands/SYN-B1', expect.anything())
    store[state] = false
  }
  await flushPromises()
  expect(store.selectedId).toBe('SYN-A1')
  await router.push('/injection?factory=huakang-b&demand=SYN-B1'); await flushPromises()
  expect(store.factory).toBe('huakang-b')
  expect(store.detail.demand.id).toBe('SYN-B1')
})

it('does not apply a late detail after close or after another demand opens, and exposes native read failures', async () => {
  const { wrapper, router, store } = await open('/injection?factory=huakang-a')
  let resolve!: (value: unknown) => void
  const normal = api.get.getMockImplementation()!
  api.get.mockImplementation((path, params) => path === '/demands/SYN-SLOW' ? new Promise(r => { resolve = r }) : normal(path, params))
  await router.push('/injection?factory=huakang-a&demand=SYN-SLOW'); await flushPromises()
  expect(wrapper.text()).toContain('正在读取所选需求')
  await router.push('/injection?factory=huakang-a&demand=SYN-A2'); await flushPromises()
  resolve(detail('SYN-SLOW')); await flushPromises()
  expect(store.detail.demand.id).toBe('SYN-A2')
  api.get.mockImplementation((path, params) => path === '/demands/MISSING' ? Promise.reject(new Error('原需求不存在')) : normal(path, params))
  await router.push('/injection?factory=huakang-a&demand=MISSING'); await flushPromises()
  expect(wrapper.get('[aria-label="需求详情"]').text()).toContain('原需求不存在')
  expect(wrapper.get('[aria-label="需求详情"]').text()).not.toContain('正在读取所选需求')
  expect(store.detail).toBeNull()
  const retry = wrapper.findAll('button').find(b => b.text() === '重新读取需求')!
  retry.element.focus()
  await retry.trigger('click'); await flushPromises()
  expect(document.activeElement).toBe(wrapper.get('[aria-label="需求详情"]').element)
  await wrapper.get('[aria-label="需求详情"]').trigger('keydown', { key: 'Escape' }); await flushPromises()
  expect(router.currentRoute.value.query.demand).toBeUndefined()
  await router.push('/injection?factory=huakang-a&demand=MISSING'); await flushPromises()
  api.get.mockImplementation(normal)
  await wrapper.findAll('button').find(b => b.text() === '重新读取需求')!.trigger('click'); await flushPromises()
  expect(store.detail.demand.id).toBe('MISSING')
  api.get.mockImplementation((path, params) => path === '/demands/SYN-SLOW' ? new Promise(r => { resolve = r }) : normal(path, params))
  await router.push('/injection?factory=huakang-a&demand=SYN-SLOW'); await flushPromises()
  // A closed URL never reopens a detail through a later source response.
  await wrapper.get('[aria-label="关闭详情"]').trigger('click'); await flushPromises()
  resolve(detail('SYN-SLOW')); await flushPromises()
  expect(store.selectedId).toBeNull()
  expect(store.detail).toBeNull()
})

it('freezes exact native query JSON without copying rows, and selected-record scope omits list filters', async () => {
  const { store, router } = await open('/injection?factory=huakang-a')
  store.filter = { field: 'dispatch_state', op: 'eq', value: 'WAIT_MATERIAL' }
  store.search = { field: 'mold_code', mode: 'prefix', text: 'SYN-' }
  store.sort = [{ field: 'mold_code', direction: 'desc' }]
  const scope = assistantSelection('injection-scheduling')!
  expect(JSON.parse(scope.filters.filter_json as string)).toEqual(store.filter)
  expect(JSON.parse(scope.filters.search_json as string)).toEqual(store.search)
  expect(JSON.parse(scope.filters.sort_json as string)).toEqual(store.sort)
  expect(scope.filters.query_summary).toContain('模号')
  store.filter.value = 'READY'
  expect(JSON.parse(scope.filters.filter_json as string).value).toBe('WAIT_MATERIAL')
  await router.push('/injection?factory=huakang-a&demand=SYN-A1'); await flushPromises()
  const selected = assistantSelection('injection-scheduling')!
  expect(selected.filters).toEqual({ factory_id: 'huakang-a' })
  expect(selected.resources[0]?.resource_id).toBe('SYN-A1')
  auth.currentUser = { id: 'synthetic-b' }; await flushPromises()
  expect(router.currentRoute.value.query.demand).toBeUndefined()
  expect(store.selectedId).toBeNull()
})

it('does not trap a revoked account in a dirty business page', async () => {
  const { router, store } = await open()
  store.dirty = true
  auth.can = () => false
  await router.push('/elsewhere'); await flushPromises()
  expect(router.currentRoute.value.path).toBe('/elsewhere')
})
