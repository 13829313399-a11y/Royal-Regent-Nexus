vi.mock('../workspaceApi',()=>import('./workspaceFixtures'))
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { CUTTING_BASE, CUTTING_WORKSPACES } from '../navigation'
import { cuttingOperationsRoutes } from '../routes'
import CuttingCutover from '../CuttingCutover.vue'
import { cutoverApi } from '../cutoverApi'
import CuttingWorkspaceShell from '../CuttingWorkspaceShell.vue'

const accessMock = vi.hoisted(() => vi.fn())

vi.mock('@/components/layout/AccountMenu.vue', () => ({ default: { template: '<span>当前账号</span>' } }))
vi.mock('../api', () => ({ cuttingApi: { access: accessMock }, errorMessage: () => '服务不可用' }))
vi.mock('../cutoverApi', async importOriginal => ({ ...await importOriginal<typeof import('../cutoverApi')>(), cutoverApi: { preview: vi.fn() } }))
let wrapper: VueWrapper | undefined
beforeEach(() => { vi.clearAllMocks(); accessMock.mockReset().mockResolvedValue({ enabled: false, schema_ready: false, permissions: [] }) })
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
  it('revalidates live authorization without losing drafts for unrelated changes or transient failures', async () => {
    const rights = { enabled: true, schema_ready: true, permissions: ['read', 'material_request'] }
    accessMock.mockResolvedValue(rights)
    const router = createRouter({ history: createMemoryHistory(), routes: [{
      path: CUTTING_BASE, component: CuttingWorkspaceShell,
      children: [{ path: 'materials', component: { template: '<input aria-label="隔离申请草稿" />' } }],
    }] })
    await router.push(`${CUTTING_BASE}/materials?factory=huakang-c`)
    wrapper = mount(RouterView, { attachTo: document.body, global: { plugins: [router] } })
    await flushPromises()
    const input = () => wrapper!.get<HTMLInputElement>('input')
    await input().setValue('保留填写')
    accessMock.mockResolvedValue({ ...rights, permissions: [...rights.permissions].reverse() })
    window.dispatchEvent(new Event('authorization-context-changed'))
    await flushPromises()
    expect(input().element.value).toBe('保留填写')
    accessMock.mockRejectedValue(new Error('offline'))
    window.dispatchEvent(new Event('authorization-context-changed'))
    await flushPromises()
    expect(input().isVisible()).toBe(false)
    expect(input().element.value).toBe('保留填写')
    accessMock.mockResolvedValue(rights)
    await wrapper!.get('[role="alert"] button').trigger('click')
    await flushPromises()
    expect(input().isVisible()).toBe(true)
    expect(input().element.value).toBe('保留填写')
    accessMock.mockResolvedValue({ ...rights, permissions: ['read'] })
    window.dispatchEvent(new Event('authorization-context-changed'))
    await flushPromises()
    expect(input().element.value).toBe('')
    await input().setValue('失权须清除')
    accessMock.mockRejectedValue({ response: { status: 403 } })
    window.dispatchEvent(new Event('cutting-authorization-recheck'))
    await flushPromises()
    expect(wrapper!.find('input').exists()).toBe(false)
    expect(wrapper!.text()).toContain('旧表单已清除')
  })
  it('clears old session input immediately and ignores a late pre-boundary authorization response', async () => {
    const rights = { enabled: true, schema_ready: true, permissions: ['read'] }
    accessMock.mockResolvedValue(rights)
    const router = createRouter({ history: createMemoryHistory(), routes: [{
      path: CUTTING_BASE, component: CuttingWorkspaceShell,
      children: [{ path: 'materials', component: { template: '<input aria-label="隔离申请草稿" />' } }],
    }] })
    await router.push(`${CUTTING_BASE}/materials?factory=huakang-c`)
    wrapper = mount(RouterView, { attachTo: document.body, global: { plugins: [router] } })
    await flushPromises()
    await wrapper.get('input').setValue('旧账号内容')
    let resolve!: (value: typeof rights) => void
    accessMock.mockReturnValueOnce(new Promise(r => { resolve = r }))
    window.dispatchEvent(new Event('authorization-context-changed'))
    accessMock.mockRejectedValue({ response: { status: 401 } })
    window.dispatchEvent(new Event('auth-session-boundary-changed'))
    await flushPromises()
    resolve(rights)
    await flushPromises()
    expect(wrapper.find('input').exists()).toBe(false)
  })
  it('opens dashboard and navigates all eight workspaces without dropping the factory', async () => {
    const router = await open(`${CUTTING_BASE}?factory=huakang-c`)
    expect(router.currentRoute.value.path).toBe(`${CUTTING_BASE}/dashboard`)
    expect(router.currentRoute.value.meta.requiresAuth).toBe(true)
    expect(wrapper!.findAll('nav[aria-label="裁床工作区导航"] a')).toHaveLength(8)
    for (const workspace of CUTTING_WORKSPACES) {
      await wrapper!.get(`nav a[href="${CUTTING_BASE}/${workspace.path}?factory=huakang-c"]`).trigger('click')
      await flushPromises()
      await vi.waitFor(async () => {
        await flushPromises()
        expect(wrapper!.get('h1').text()).toBe(workspace.title)
      }, { timeout: 10000 })
      if (workspace.path === 'master') {
        expect(wrapper!.text()).toContain('基础资料尚未启用')
      } else if (workspace.path === 'reporting') {
        expect(wrapper!.text()).toContain('每日填数尚未启用')
        expect(wrapper!.find('form').exists()).toBe(false)
      } else if (workspace.path === 'costs') {
        expect(wrapper!.text()).toContain('实际材料费用尚未启用')
        expect(wrapper!.find('form').exists()).toBe(false)
      } else if (workspace.path === 'closing') {
        expect(wrapper!.text()).toContain('月结前核对尚未启用')
        // P5a keeps a read-only preparation form; disabled access must still
        // block requests, including a direct submit that bypasses the button.
        const cutover = wrapper!.getComponent(CuttingCutover)
        expect(cutover.get('button[type="submit"]').attributes('disabled')).toBeDefined()
        await cutover.get('form').trigger('submit')
        await flushPromises()
        expect(cutoverApi.preview).not.toHaveBeenCalled()
        expect(wrapper!.findAll('form')).toHaveLength(cutover.findAll('form').length)
      } else if (workspace.path === 'planning' || workspace.path === 'materials') {
        expect(wrapper!.text()).toContain('尚不能录入、保存或结算业务数据')
        expect(wrapper!.text()).toContain(workspace.empty)
      }
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
    expect(wrapper!.text()).toContain('月结前核对尚未启用')
    expect(wrapper!.text()).toContain('尚未冻结或锁月')
    expect(wrapper!.find('table').exists()).toBe(false)
    await router.push(`${CUTTING_BASE}/planning?factory=huakang-c`)
    await flushPromises()
    expect(wrapper!.get('h2').text()).toBe('订单总台账')
    expect(wrapper!.text()).toContain('当前阶段必需物料')
    expect(wrapper!.find('input').exists()).toBe(false)
  })
})
