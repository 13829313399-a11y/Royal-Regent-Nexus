import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { sprayProductionApi as api, type SpraySummary } from '@/api/sprayProduction'
import SprayProductionView from '@/views/SprayProductionView.vue'

vi.mock('@/api/sprayProduction', () => ({sprayProductionApi:{summary:vi.fn(),collection:vi.fn(),balances:vi.fn(),command:vi.fn(),preferences:vi.fn()}}))
vi.mock('@/lib/http', () => ({http:{get:vi.fn()}}))

/* 工作区外壳测试：九个业务入口、分组、当前状态与厂区上下文必须保持可达，
   且真实加载 / 未选厂区 / 权限状态不能被视觉改动破坏。 */
const snapshot = (factory: string, permissions: string[]): SpraySummary => ({factory_id:factory,revision:1,as_of:'2026-09-11T00:00:00Z',data_mode:'live',coverage:'no_data',counts:{orders:3,running:1,planned:2,resources:4},permissions})
const paths = ['overview','orders','schedule','reports','wip','logistics','finance','master','imports']
const Shell = { template: '<div><RouterView /></div>' }

async function routerAt(path: string): Promise<Router> {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: Shell }, { path: '/modules/production/spray-production/:page/:id?', component: Shell }] })
  await router.push(path)
  await router.isReady()
  return router
}
function notice(wrapper: { get(selector: string): { text(): string } }) { return wrapper.get('[role="status"]').text() }

beforeEach(() => {
  vi.resetAllMocks()
  setActivePinia(createPinia())
  window.matchMedia = vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }) as unknown as typeof window.matchMedia
  vi.mocked(api.summary).mockImplementation(async factory => snapshot(factory, ['read','plan','report','order_write','logistics','master_write','export','cost_read']))
  vi.mocked(api.collection).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 1000 })
  vi.mocked(api.balances).mockResolvedValue({})
  vi.mocked(api.preferences).mockResolvedValue([])
})

describe('spray workspace shell', () => {
  it('keeps all nine business entries reachable and grouped by workflow stage', async () => {
    setActivePinia(createPinia())
    const router = await routerAt('/modules/production/spray-production/overview?factory=huaxing')
    const wrapper = mount(SprayProductionView, { global: { plugins: [router] } })
    await flushPromises()
    const links = wrapper.findAll('.spray-nav a')
    expect(links).toHaveLength(9)
    expect(links.map(link => link.text())).toEqual(['生产总览','工单交付','排产画布','现场报工','在制与质量','收发交接','经营核算','资料中心','历史导入'])
    for (const path of paths) expect(wrapper.find(`.spray-nav a[href="/modules/production/spray-production/${path}?factory=huaxing"]`).exists()).toBe(true)
    expect(wrapper.findAll('.spray-nav-label').map(label => label.text())).toEqual(['总览','执行','账务','资料'])
    expect(wrapper.get('.spray-nav-current').text()).toContain('总览 · 生产总览')
    expect(wrapper.get('.spray-scope-chip').text()).toContain('华兴')
    wrapper.unmount()
  })

  it('marks the current navigation entry and keeps the group active on a detail route', async () => {
    setActivePinia(createPinia())
    const router = await routerAt('/modules/production/spray-production/orders/order-1?factory=huaxing')
    const wrapper = mount(SprayProductionView, { global: { plugins: [router] } })
    await flushPromises()
    const active = wrapper.findAll('.spray-nav a.router-link-active')
    expect(active).toHaveLength(1)
    expect(active[0]!.text()).toBe('工单交付')
    expect(active[0]!.attributes('aria-current')).toBe('page')
    expect(wrapper.get('.spray-nav-current').text()).toContain('执行 · 工单交付')
    wrapper.unmount()
  })

  it('keeps factory selection and live status in the workspace header', async () => {
    setActivePinia(createPinia())
    const router = await routerAt('/modules/production/spray-production/schedule?factory=huakang-a')
    const wrapper = mount(SprayProductionView, { global: { plugins: [router] } })
    await flushPromises()
    const factory = wrapper.get('select[aria-label="执行厂区"]')
    expect((factory.element as HTMLSelectElement).value).toBe('huakang-a')
    expect(wrapper.get('.spray-topbar').text()).toContain('执行厂区 · 华康 A')
    expect(notice(wrapper)).toContain('更新于')
    const bar = wrapper.get('.spray-workspace-bar')
    expect(bar.find('select[aria-label="执行厂区"]').exists()).toBe(true)
    expect(bar.get('select[aria-label="导出账册"]').exists()).toBe(true)
    expect(bar.get('.spray-help').text()).toContain('当前页')
    wrapper.unmount()
  })

  it('shows the truncation warning and the cost permission limit without removing the ledger choice', async () => {
    setActivePinia(createPinia())
    vi.mocked(api.summary).mockImplementation(async factory => snapshot(factory, ['read','report','export']))
    vi.mocked(api.collection).mockImplementation(async (_scope, kind, _signal, page = 1) => ({ items: kind === 'orders' && page === 1 ? [{ id: 'o-1', document_no: '0000123' }] : [], total: kind === 'orders' ? 1200 : 0, page, page_size: 1000 }))
    const router = await routerAt('/modules/production/spray-production/orders?factory=huaxing')
    const wrapper = mount(SprayProductionView, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('当前加载各类最近 1,000 条记录')
    expect(wrapper.findAll('[role="alert"]').some(node => node.text().includes('并非完整账册'))).toBe(true)
    const ledger = wrapper.get('select[aria-label="导出账册"]')
    expect(ledger.findAll('option').map(option => option.text())).toEqual(['工单','送退货凭据','容器往来'])
    expect(wrapper.findAll('.spray-nav a')).toHaveLength(9)
    wrapper.unmount()
  })

  it('asks for a factory without hiding the business entries or inventing data', async () => {
    setActivePinia(createPinia())
    const router = await routerAt('/modules/production/spray-production/overview?factory=group')
    const wrapper = mount(SprayProductionView, { global: { plugins: [router] } })
    await flushPromises()
    expect(api.summary).not.toHaveBeenCalled()
    expect(wrapper.get('.spray-empty').text()).toContain('选择执行厂区')
    expect(wrapper.get('.spray-scope-chip').text()).toContain('集团视图')
    expect(wrapper.findAll('.spray-nav a')).toHaveLength(9)
    expect(wrapper.find('#spray-main table').exists()).toBe(false)
    wrapper.unmount()
  })

  it('reports the real loading state while the factory snapshot is pending', async () => {
    setActivePinia(createPinia())
    let release!: (value: SpraySummary) => void
    vi.mocked(api.summary).mockImplementation(() => new Promise(resolve => { release = resolve }))
    const router = await routerAt('/modules/production/spray-production/overview?factory=huaxing')
    const wrapper = mount(SprayProductionView, { global: { plugins: [router] } })
    await flushPromises()
    expect(notice(wrapper)).toContain('正在读取本厂数据')
    expect(wrapper.get('.spray-empty').text()).toContain('正在读取工单、批次与资源')
    release(snapshot('huaxing', ['read']))
    await flushPromises()
    expect(notice(wrapper)).toContain('更新于')
    wrapper.unmount()
  })
})
