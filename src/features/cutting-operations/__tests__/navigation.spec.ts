import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { CUTTING_BASE, CUTTING_WORKSPACES } from '../navigation'
import { cuttingOperationsRoutes } from '../routes'

vi.mock('@/components/layout/AccountMenu.vue', () => ({ default: { template: '<span>当前账号</span>' } }))
let wrapper: VueWrapper | undefined
afterEach(() => { wrapper?.unmount(); wrapper = undefined })

async function open(path: string) {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    ...cuttingOperationsRoutes,
    { path: '/modules/production', component: { template: '<div>生产部首页</div>' } },
  ] })
  await router.push(path)
  await router.isReady()
  wrapper = mount(RouterView, { global: { plugins: [router] } })
  await flushPromises()
  return router
}

describe('cutting workspace entry', () => {
  it('opens planning and navigates all six workspaces without dropping the factory', async () => {
    const router = await open(`${CUTTING_BASE}?factory=huakang-c`)
    expect(router.currentRoute.value.path).toBe(`${CUTTING_BASE}/planning`)
    expect(router.currentRoute.value.meta.requiresAuth).toBe(true)
    expect(wrapper!.findAll('nav[aria-label="裁床工作区导航"] a')).toHaveLength(6)
    for (const workspace of CUTTING_WORKSPACES) {
      await wrapper!.get(`nav a[href="${CUTTING_BASE}/${workspace.path}?factory=huakang-c"]`).trigger('click')
      await flushPromises()
      expect(wrapper!.get('h1').text()).toBe(workspace.title)
      expect(wrapper!.text()).toContain('尚不能录入、保存或结算业务数据')
      expect(wrapper!.text()).toContain(workspace.empty)
      expect(router.currentRoute.value.query.factory).toBe('huakang-c')
    }
    await wrapper!.get('a.cutting-back').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/modules/production?factory=huakang-c')
  })
  it.each(['', '?factory=group', '?factory=huaxing', '?factory=huakang-d', '?factory=bad', '?factory=huakang-c&factory=huakang-d'])(
    'rejects missing, foreign or ambiguous factory: %s', async query => {
      const router = await open(`${CUTTING_BASE}/master${query}`)
      expect(router.currentRoute.value.path).toBe('/modules/production')
      expect(wrapper!.find('.cutting-shell').exists()).toBe(false)
    },
  )
  it('rechecks query-only changes while the same parent remains mounted', async () => {
    const router = await open(`${CUTTING_BASE}/planning?factory=huakang-c`)
    await router.push(`${CUTTING_BASE}/planning?factory=huakang-d`)
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/modules/production?factory=huakang-d')
    expect(wrapper!.find('.cutting-shell').exists()).toBe(false)
  })
  it('resets subviews on workspace changes and shows unfinished capabilities explicitly', async () => {
    const router = await open(`${CUTTING_BASE}/closing?factory=huakang-c`)
    await wrapper!.get('.cutting-section-nav button:nth-child(2)').trigger('click')
    expect(wrapper!.get('h2').text()).toBe('外发对账')
    expect(wrapper!.text()).toContain('外发对账尚未开放')
    expect(wrapper!.find('table').exists()).toBe(false)
    await router.push(`${CUTTING_BASE}/planning?factory=huakang-c`)
    await flushPromises()
    expect(wrapper!.get('h2').text()).toBe('订单总台账')
    expect(wrapper!.text()).toContain('当前阶段必需物料')
    expect(wrapper!.find('input').exists()).toBe(false)
  })
})
