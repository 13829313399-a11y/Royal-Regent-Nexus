import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, reactive, ref } from 'vue'
import { createRouter, createMemoryHistory, RouterView } from 'vue-router'
import { threeDPrintingApi } from '@/api/threeDPrinting'
import { http } from '@/lib/http'
import { assistantSelection } from '@/features/assistant/selection'
import { canChangeFactory } from '@/lib/factoryChangeGuard'
import { useWorkspaceContext } from '../context'
import type { useWorkspace } from '../composables/useWorkspace'
import { guardThreeDNavigation } from '../navigationGuard'
import ThreeDPrintingManagementView from '@/views/ThreeDPrintingManagementView.vue'
import LegacyDialog from '../components/LegacyDialog.vue'
import type { ThreeDDashboard, ThreeDPrinter } from '@/types/threeDPrinting'

const auth = reactive({ currentUser: { id: 'syn-a', identity: { employment_epoch: 1 } }, authorizationVersion: 1,
  grants: [], can: (permission: string) => permission === 'three_d_printing:read' })
const app = reactive({ activeProductionFactory: { id: 'huakang-a' }, setActiveFactory(id: string) { this.activeProductionFactory.id = id } })
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))
vi.mock('@/stores/app', () => ({ useAppStore: () => app }))
vi.mock('@/api/threeDPrinting', () => ({ threeDPrintingApi: { dashboard: vi.fn(), collection: vi.fn(), updateSettings: vi.fn(), audit: vi.fn(), deletedRecords: vi.fn() } }))
vi.mock('@/lib/http', () => ({ http: { get: vi.fn() }, getApiErrorMessage: (e: Error) => e.message }))
vi.mock('@/composables/useThreeDLive', () => ({ useThreeDLive: () => ({ connected: { value: false }, start: vi.fn(), stop: vi.fn() }) }))
const api = vi.mocked(threeDPrintingApi)
const wrappers: ReturnType<typeof mount>[] = []
let workspace: ReturnType<typeof useWorkspace>
const editorOpen = ref(false)
const printer = (id: string) => ({ id, machine_no: id === 'SYN-1' ? 1 : 2, name: id, model: 'Bambu',
  connected: false, state: 'STALE', status_stale: true, last_seen_at: '2026-10-25T08:45:00+08:00',
  current_file: `Task-${id}`, progress_percent: 40, remaining_minutes: 20,
  nozzle_temperature: 20, bed_temperature: 20 } as ThreeDPrinter)
function dashboard() { return {
  printers: [printer('SYN-1'), printer('SYN-2')], products: [], materials: [], records: [], schedules: [], maintenance: [],
  inventory: [], inventory_movements: [], day_statuses: [], day_off_dates: [], summary: {},
  settings: { machine_count: 11, electricity_per_machine_day: 1.5, labor_per_day: 220, material_loss_rate: 1.2, profit_rate_percent: 40, revision: 1 },
} as unknown as ThreeDDashboard }
beforeEach(() => {
  vi.clearAllMocks()
  editorOpen.value = false
  auth.currentUser = { id: 'syn-a', identity: { employment_epoch: 1 } }
  auth.authorizationVersion = 1
  auth.can = permission => ['three_d_printing:read', 'three_d_printing:operate'].includes(permission)
  app.activeProductionFactory.id = 'huakang-a'
  api.dashboard.mockImplementation(async () => dashboard())
  api.collection.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 })
  vi.mocked(http.get).mockImplementation(async path => ({ data: { printer: printer(String(path).split('/').at(-2)!), events: [], commands: [] } }))
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })))
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
})
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()); document.body.innerHTML = ''; vi.unstubAllGlobals() })
async function open(url = '/printers?factory=huakang-a&tab=machines&printer=SYN-1') {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/printers', name: 'three-d-printing-management', component: ThreeDPrintingManagementView },
    { path: '/other', component: { template: '<p>其他模块</p>' } },
    { path: '/', component: { template: '<p>首页</p>' } },
  ] })
  router.beforeEach((to, from) => {
    if (!guardThreeDNavigation(to, from)) return false
    if (typeof to.query.factory === 'string') app.setActiveFactory(to.query.factory)
  })
  await router.push(url)
  const wrapper = mount(defineComponent({ components: { RouterView }, template: '<RouterView />' }), {
    attachTo: document.body, global: { plugins: [router], stubs: {
      transition: false,
      AccountMenu: defineComponent({ setup() {
        workspace = useWorkspaceContext()
        return () => h('div', [h('span', '账号'), h(LegacyDialog, { title: '编辑记录', open: editorOpen.value }, { default: () => h('input', { value: '未保存草稿' }) })])
      } }),
      OverviewPage: true, RecordsPage: true, ProductsPage: true, MaterialsPage: true,
      SchedulesPage: true, MaintenancePage: true, ReportsPage: true, OperationsPage: true, MigrationPage: true,
    } },
  })
  wrappers.push(wrapper); await flushPromises()
  return { wrapper, router }
}
const panel = () => document.querySelector<HTMLElement>('.printer-detail')!
async function escape() {
  panel().dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
  await flushPromises(); await vi.waitFor(() => expect(panel()).toBeNull())
}

it('opens a factory-bound native printer, preserves its observation time and retains a removable assistant selection after close', async () => {
  const trigger = document.createElement('button'); trigger.textContent = '原机台入口'; document.body.append(trigger); trigger.focus()
  const { wrapper, router } = await open()
  expect(http.get).toHaveBeenCalledWith('/three-d-printing/printers/SYN-1/timeline', expect.objectContaining({ params: { factory_id: 'huakang-a' } }))
  expect(panel().textContent).toContain('10/25 08:45:00')
  expect(panel().textContent).toContain('失联或过期不代表机器已物理停机')
  expect(assistantSelection('three-d-printing')?.resources[0]?.resource_id).toBe('SYN-1')
  await escape()
  expect(router.currentRoute.value.query.printer).toBeUndefined()
  expect(panel()).toBeNull()
  expect(document.activeElement).toBe(trigger)
  expect(wrapper.text()).toContain('曜灵查询范围：1 号机')
  await wrapper.findAll('button').find(b => b.text() === '清除选择')!.trigger('click')
  expect(assistantSelection('three-d-printing')?.resources).toEqual([])
  const card = wrapper.findAll('.legacy-machine')[1]!
  card.element.focus(); await card.trigger('click'); await flushPromises()
  expect(router.currentRoute.value.query.printer).toBe('SYN-2')
  await escape(); expect(document.activeElement).toBe(card.element)
})

it('never carries a printer identifier from a different factory into the forced Huakang A route', async () => {
  const { router } = await open('/printers?factory=huakang-b&tab=machines&printer=SYN-1')
  expect(router.currentRoute.value.query.factory).toBe('huakang-a')
  expect(router.currentRoute.value.query.printer).toBeUndefined()
  expect(http.get).not.toHaveBeenCalled()
  expect(assistantSelection('three-d-printing')?.resources).toEqual([])
})

it('clears inaccessible facts, retries on the native endpoint and keeps Escape reachable from the refresh control', async () => {
  const { router } = await open()
  vi.mocked(http.get).mockRejectedValueOnce({ isAxiosError: true, response: { status: 404 }, message: '原机台不存在' })
  const refresh = panel().querySelector<HTMLButtonElement>('.refresh-button')!
  refresh.focus(); refresh.click(); await flushPromises()
  expect(panel().textContent).toContain('原机台不存在')
  expect(panel().textContent).toContain('机台不可用')
  expect(panel().textContent).not.toContain('等待连接')
  expect(panel().textContent).not.toContain('最近状态变化')
  expect(panel().textContent).not.toContain('最后上报')
  expect(panel().textContent).not.toContain('Task-SYN-1')
  expect(assistantSelection('three-d-printing')?.resources).toEqual([])
  expect(document.activeElement).toBe(panel())
  refresh.click(); await flushPromises()
  expect(panel().textContent).toContain('Task-SYN-1')
  await escape(); expect(router.currentRoute.value.query.printer).toBeUndefined()
})

it('ignores a late detail after another printer opens or the selected URL closes', async () => {
  const { router } = await open('/printers?factory=huakang-a&tab=machines')
  let resolve!: (value: unknown) => void
  vi.mocked(http.get).mockImplementationOnce(() => new Promise(r => { resolve = r }))
  await router.push('/printers?factory=huakang-a&tab=machines&printer=SYN-SLOW'); await flushPromises()
  expect(panel().textContent).toContain('正在读取所选机台')
  await router.push('/printers?factory=huakang-a&tab=machines&printer=SYN-2'); await flushPromises()
  resolve({ data: { printer: printer('SYN-SLOW'), events: [], commands: [] } }); await flushPromises()
  expect(panel().textContent).toContain('Task-SYN-2')
  expect(panel().textContent).not.toContain('SYN-SLOW')
  await escape(); expect(panel()).toBeNull()
})

it('protects settings and pending writes before route, tab or factory mutation and preserves the dirty form across refresh', async () => {
  const { router } = await open('/printers?factory=huakang-a&tab=audit')
  workspace.settingsForm.labor_per_day = 333
  await workspace.loadDashboard(true)
  expect(workspace.settingsForm.labor_per_day).toBe(333)
  expect(workspace.settingsDirty.value).toBe(true)
  workspace.activeTab.value = 'machines'
  expect(workspace.activeTab.value).toBe('audit')
  expect(canChangeFactory()).toBe(false)
  await router.push('/printers?factory=huakang-b&printer=SYN-2')
  expect(router.currentRoute.value.query.factory).toBe('huakang-a')
  expect(app.activeProductionFactory.id).toBe('huakang-a')
  workspace.resetSettings(); expect(workspace.settingsDirty.value).toBe(false)
  expect(workspace.errorMessage.value).toBe('')
  workspace.saving.value = true
  await router.push('/other'); expect(router.currentRoute.value.path).toBe('/printers')
  workspace.saving.value = false
  await router.push('/other'); expect(router.currentRoute.value.path).toBe('/other')
})

it('protects an open native editor without replaying a denied printer navigation after it closes', async () => {
  const { router } = await open('/printers?factory=huakang-a&tab=machines')
  editorOpen.value = true; await flushPromises()
  await router.push('/printers?factory=huakang-a&tab=machines&printer=SYN-1')
  expect(router.currentRoute.value.query.printer).toBeUndefined()
  editorOpen.value = false; await flushPromises()
  expect(panel()).toBeNull()
  await workspace.openPrinter('SYN-1'); await flushPromises()
  expect(panel().textContent).toContain('Task-SYN-1')
})

it('keeps committed settings and revision when the follow-up read fails, and keeps an unsuccessful draft', async () => {
  await open('/printers?factory=huakang-a&tab=audit')
  workspace.settingsForm.labor_per_day = 333
  api.updateSettings.mockResolvedValue({ ...dashboard().settings, labor_per_day: 333, revision: 2 })
  api.dashboard.mockRejectedValueOnce(new Error('后续读取断开'))
  await workspace.saveSettings()
  expect(workspace.settingsForm.labor_per_day).toBe(333)
  expect(workspace.settingsForm.revision).toBe(2)
  expect(workspace.settingsDirty.value).toBe(false)
  workspace.settingsForm.labor_per_day = 444
  api.updateSettings.mockRejectedValueOnce(new Error('写入失败'))
  await workspace.saveSettings()
  expect(workspace.settingsForm.labor_per_day).toBe(444)
  expect(workspace.settingsDirty.value).toBe(true)
  expect(workspace.errorMessage.value).toBe('写入失败')
})

it('drops old account data and selection on account/epoch changes and permits a revoked dirty account to leave', async () => {
  const { router, wrapper } = await open()
  const previous = workspace
  workspace.settingsForm.labor_per_day = 444
  auth.currentUser = { id: 'syn-b', identity: { employment_epoch: 2 } }
  await flushPromises()
  expect(workspace).not.toBe(previous)
  expect(panel()).toBeNull()
  expect(router.currentRoute.value.query.printer).toBeUndefined()
  expect(assistantSelection('three-d-printing')?.resources).toEqual([])
  expect(workspace.settingsForm.labor_per_day).toBe(220)
  workspace.settingsForm.labor_per_day = 555
  auth.can = () => false; await flushPromises()
  expect(wrapper.text()).toContain('无华康 A')
  expect(assistantSelection('three-d-printing')).toBeNull()
  await router.push('/other'); expect(router.currentRoute.value.path).toBe('/other')
})
