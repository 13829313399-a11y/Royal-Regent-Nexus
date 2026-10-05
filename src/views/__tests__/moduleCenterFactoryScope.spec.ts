import { mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import DepartmentTabs from '@/components/modules/DepartmentTabs.vue'
import ModuleCard from '@/components/modules/ModuleCard.vue'
import PermissionMatrix from '@/components/modules/PermissionMatrix.vue'
import TodoQueue from '@/components/modules/TodoQueue.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import {
  departmentMap,
  departmentModuleRegistry,
  moduleDepartmentIds,
  type EnterpriseModule,
  type ModuleDepartmentId,
} from '@/data/enterpriseMock'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import ModuleCenterView from '@/views/ModuleCenterView.vue'

const routeState = vi.hoisted(() => ({
  path: '/modules/engineering',
  name: 'modules-department',
  params: { department: 'engineering' } as { department: string },
  query: {} as Record<string, string>,
}))
const routerPushMock = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({
  RouterLink: {
    name: 'RouterLink',
    props: ['to'],
    template: '<a><slot /></a>',
  },
  useRoute: () => routeState,
  useRouter: () => ({
    push: routerPushMock,
  }),
}))

type ModuleSnapshot = Pick<EnterpriseModule, 'id' | 'title' | 'owner' | 'stats' | 'route' | 'href' | 'todos'> & {
  childLabels: string[]
  metrics: Array<{ label: string; value: string }>
}

function moduleSnapshots(wrapper: VueWrapper): ModuleSnapshot[] {
  return wrapper.findAllComponents(ModuleCard).map((card) => {
    const module = card.props('module') as EnterpriseModule

    return {
      id: module.id,
      title: module.title,
      owner: module.owner,
      stats: module.stats,
      route: module.route,
      href: module.href,
      todos: [...module.todos],
      childLabels: module.children.map((child) => child.label),
      metrics: module.statusMetrics.map((metric) => ({ label: metric.label, value: metric.value })),
    }
  })
}

function sharedStructure(modules: ModuleSnapshot[]) {
  return modules.map(({ id, title, childLabels, metrics }) => ({
    id,
    title,
    childLabels,
    metricLabels: metrics.map(({ label }) => label),
  }))
}

function expectFactoryScopedRoutes(modules: ModuleSnapshot[], factoryId: 'huakang-c' | 'huakang-d') {
  const internalTargets = modules.flatMap((module) => [module.route, module.href]
    .filter((target): target is string => Boolean(target) && !/^https?:\/\//i.test(target!)))

  expect(internalTargets.length).toBeGreaterThan(0)
  for (const target of internalTargets) {
    const url = new URL(target, 'http://nexus.local')
    expect(url.pathname.startsWith('/')).toBe(true)
    if (['/carton-supplier', '/carton-supplier/carton-mark'].includes(url.pathname)) {
      expect(url.searchParams.get('factory')).toBeNull()
      continue
    }
    expect(url.searchParams.get('factory')).toBe(factoryId)
    expect(target).not.toContain('factory=huaxing')
  }
}

function expectNoForeignFactoryData(
  wrapper: VueWrapper,
  modules: ModuleSnapshot[],
  factoryId: 'huakang-c' | 'huakang-d',
  factoryName: '华康C' | '华康D',
) {
  const serializedVisibleData = JSON.stringify({
    moduleTodos: modules.flatMap((module) => module.todos),
    departmentTodos: wrapper.getComponent(TodoQueue).props('items'),
  })

  const foreignReferences = [
    ['华兴', '华兴'],
    ['华康A', 'A 厂'],
    ['华康B', 'B 厂'],
    ['华康C', 'C 厂'],
    ['华康D', 'D 厂'],
  ].filter(([factoryReference]) => factoryReference !== factoryName).flat()

  for (const foreignReference of foreignReferences) {
    expect(serializedVisibleData).not.toContain(foreignReference)
  }

  expect(modules.every((module) => module.todos.length === 0)).toBe(true)
  expect(wrapper.getComponent(TodoQueue).props('items')).toEqual([])
  expect(modules.some((module) => module.stats === `${factoryName} · 当前暂无本厂数据`)).toBe(true)
  expect(modules.some((module) => module.metrics.every(({ value }) => value === '—'))).toBe(true)
  expectFactoryScopedRoutes(modules, factoryId)
}

function expectSharedPageComponents(wrapper: VueWrapper) {
  expect(wrapper.findComponent(DepartmentTabs).exists()).toBe(true)
  expect(wrapper.findComponent(PermissionMatrix).exists()).toBe(true)
  expect(wrapper.findComponent(TodoQueue).exists()).toBe(true)
}

describe('module center factory scope', () => {
  beforeEach(() => {
    routeState.path = '/modules/engineering'
    routeState.params.department = 'engineering'
    routeState.query = {}
    routerPushMock.mockReset()
  })

  it('routes supplier accounts to their own collaboration and read-only carton mark pages', async () => {
    routeState.path = '/modules/pmc-warehouse'
    routeState.params.department = 'pmc-warehouse'
    const pinia = createPinia()
    setActivePinia(pinia)
    useAppStore().setActiveFactory('huaxing')
    const auth = useAuthStore()
    const wrapper = mount(ModuleCenterView, { global: { plugins: [pinia] } })
    const getModule = (id: string) => wrapper.findAllComponents(ModuleCard)
      .find(card => (card.props('module') as EnterpriseModule).id === id)!.props('module') as EnterpriseModule

    expect(wrapper.findAllComponents(ModuleCard).some(card => (card.props('module') as EnterpriseModule).id === 'carton-procurement')).toBe(false)
    expect(getModule('carton-supplier').route).toBe('/carton-supplier')
    expect(getModule('carton-mark-check').route).toBe('/carton-supplier/carton-mark')

    auth.factoryScopes = ['*']
    auth.permissions = ['carton_supplier:read']
    auth.effectiveAccess = [{ permission_code: 'carton_supplier:read', factory_id: '*', department: '*', effect: 'allow', allowed: true, source_type: 'user_override', source_ids: ['supplier-read'] }]
    auth.hasEffectiveAccessSnapshot = true
    await nextTick()
    expect(getModule('carton-supplier').route).toBe('/carton-supplier')
    expect(getModule('carton-mark-check').route).toBe('/carton-supplier/carton-mark')

    auth.permissions = ['carton_supplier:read', 'carton_procurement:read', 'carton_mark:read']
    await nextTick()
    expect(getModule('carton-procurement').route).toBe('/modules/pmc-warehouse/carton-procurement?factory=huaxing')
    expect(getModule('carton-supplier').route).toBe('/carton-supplier')
    auth.permissions = ['carton_procurement:read', 'carton_mark:read']
    auth.effectiveAccess = []
    await nextTick()
    expect(getModule('carton-supplier').route).toBe('/carton-supplier-management?factory=huaxing')
    expect(getModule('carton-mark-check').route).toBe('/modules/pmc-warehouse/carton-mark-check?factory=huaxing')
    wrapper.unmount()
  })

  it('registers the 3D printing card only for Huakang A', () => {
    const module = departmentModuleRegistry.production.modules.find(
      (item) => item.id === 'three-d-printing',
    )

    expect(module?.factoryIds).toEqual(['huakang-a'])
    expect(module?.owner).toBe('华康A · 3D部门')
  })

  it('opens the UV card only for current Huakang A permission and reacts to revocation', async () => {
    routeState.path = '/modules/production'
    routeState.params.department = 'production'
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useAppStore()
    store.setActiveFactory('huakang-a')
    const wrapper = mount(ModuleCenterView, { global: { plugins: [pinia] } })
    const findCard = () => wrapper.findAllComponents(ModuleCard).find(
      (item) => item.props('module').id === 'uv-printing',
    )
    const card = findCard()!
    expect(card.text()).toContain('权限待开通')
    expect(card.props('module').detailPage).toBe(false)
    expect(card.find('a').exists()).toBe(false)
    expect(card.find('.portal-module-card__children').exists()).toBe(false)
    expect(card.attributes('role')).toBeUndefined()
    expect(card.attributes('tabindex')).toBeUndefined()
    await card.trigger('click')
    await card.trigger('keydown', { key: 'Enter' })
    await card.trigger('keydown', { key: ' ' })
    expect(routerPushMock).not.toHaveBeenCalled()
    const auth = useAuthStore()
    auth.applySession({
      id: 'uv-user', username: 'uv-user', display_name: 'UV user', roles: [],
      permissions: ['uv_ops:read'], grants: [], factory_scopes: ['huakang-a'],
      department_scopes: ['production'], force_password_change: false,
      profile: {
        primary_factory_id: 'huakang-a', primary_department: 'production',
        position: '', confirmation_status: 'confirmed',
      },
      effective_access: [{
        permission_code: 'uv_ops:read', factory_id: 'huakang-a', department: 'production',
        effect: 'allow', allowed: true, source_type: 'role_binding', source_ids: ['uv'],
      }],
    })
    await nextTick()
    expect(findCard()!.props('module').detailPage).toBe(true)
    expect(findCard()!.find('a').exists()).toBe(true)
    await findCard()!.trigger('click')
    expect(routerPushMock).toHaveBeenCalledWith('/modules/production/uv-printing/live?factory=huakang-a')
    for (const factory of ['group', 'huaxing', 'huakang-b', 'huakang-c', 'huakang-d', 'huadeng'] as const) {
      store.setActiveFactory(factory)
      await nextTick()
      expect(findCard()).toBeUndefined()
    }
    store.setActiveFactory('huakang-a')
    await nextTick()
    expect(findCard()?.text()).toContain('工作区')
    auth.applySession({ ...auth.currentUser!, permissions: [], effective_access: [] })
    await nextTick()
    expect(findCard()?.text()).toContain('权限待开通')
    expect(findCard()!.find('a').exists()).toBe(false)
    wrapper.unmount()
  })

  it.each(['huaxing', 'huakang-a', 'huakang-b', 'huadeng'] as const)(
    'keeps only an inert production placeholder in %s',
    async (factoryId) => {
      routeState.path = '/modules/production'
      routeState.params.department = 'production'
      const pinia = createPinia()
      setActivePinia(pinia)
      useAppStore().setActiveFactory(factoryId)
      const wrapper = mount(ModuleCenterView, { global: { plugins: [pinia] } })
      const card = wrapper.findAllComponents(ModuleCard).find(
        (item) => item.props('module').id === 'spray-production',
      )!

      expect(card.text()).toContain('待重构')
      expect(card.props('module').detailPage).toBe(false)
      expect(card.find('a').exists()).toBe(false)
      expect(card.find('.portal-module-card__metrics').exists()).toBe(false)
      expect(card.find('.portal-module-card__children').exists()).toBe(false)
      expect(card.attributes('role')).toBeUndefined()
      expect(card.attributes('tabindex')).toBeUndefined()
      await card.trigger('click')
      await card.trigger('keydown', { key: 'Enter' })
      expect(routerPushMock).not.toHaveBeenCalled()
      wrapper.unmount()
    },
  )

  it('shows the cutting entry only in Huakang C and supports keyboard entry', async () => {
    routeState.params.department = 'production'
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useAppStore()
    store.setActiveFactory('huakang-c')
    const wrapper = mount(ModuleCenterView, { global: { plugins: [pinia] } })
    const card = wrapper.findAllComponents(ModuleCard).find(item => item.props('module').id === 'cutting')!
    expect(card.props('module').stats).toBe('工作区已开放 · 业务待接入')
    await card.trigger('keydown', { key: 'Enter' })
    expect(routerPushMock).toHaveBeenCalledWith('/modules/production/cutting?factory=huakang-c')
    for (const factory of ['group', 'huaxing', 'huakang-a', 'huakang-b', 'huakang-d', 'huadeng'] as const) {
      store.setActiveFactory(factory)
      await nextTick()
      expect(wrapper.findAllComponents(ModuleCard).some(item => item.props('module').id === 'cutting')).toBe(false)
    }
    wrapper.unmount()
  })

  it.each(moduleDepartmentIds)(
    'shares the %s module structure while keeping Huakang C and D routes isolated',
    async (departmentId: ModuleDepartmentId) => {
      routeState.path = `/modules/${departmentId}`
      routeState.params.department = departmentId
      const pinia = createPinia()
      setActivePinia(pinia)
      const store = useAppStore()
      store.setActiveFactory('huakang-c')

      const wrapper = mount(ModuleCenterView, {
        global: {
          plugins: [pinia],
        },
      })
      await nextTick()

      expectSharedPageComponents(wrapper)
      expect(wrapper.getComponent(PageHeader).props('title')).toBe(
        `华康C · ${departmentMap[departmentId].name}模块中心`,
      )

      const huakangCModules = moduleSnapshots(wrapper)
      const expectedHuakangCModules = departmentModuleRegistry[departmentId].modules
        .filter((module) => !module.factoryIds?.length || module.factoryIds.includes('huakang-c'))
        .filter((module) => departmentId !== 'pmc-warehouse' || module.id !== 'carton-procurement')
      expect(huakangCModules).toHaveLength(expectedHuakangCModules.length)
      expect(huakangCModules.map(({ id, title, childLabels }) => ({ id, title, childLabels }))).toEqual(
        expectedHuakangCModules.map((module) => ({
          id: module.id,
          title: module.title,
          childLabels: module.children.filter(child => departmentId !== 'pmc-warehouse' || module.id !== 'carton-mark-check' || ['客人 Excel', '印刷 PDF'].includes(child.label)).map((child) => child.label),
        })),
      )
      expectNoForeignFactoryData(wrapper, huakangCModules, 'huakang-c', '华康C')
      if (departmentId === 'pmc-warehouse') {
        const rawMaterialModule = huakangCModules.find((module) => module.id === 'raw-material-management')
        expect(rawMaterialModule?.stats).toBe('华康C · 公共原料资料已接入')
        expect(rawMaterialModule?.metrics).toContainEqual({ label: '原料', value: '共享' })
      }

      store.setActiveFactory('huakang-d')
      await nextTick()

      expect(wrapper.getComponent(PageHeader).props('title')).toContain('华康D · ')
      expect(wrapper.getComponent(PageHeader).props('title')).not.toContain('华兴')
      const huakangDModules = moduleSnapshots(wrapper)
      // Cutting is exclusive to Huakang C; the shared module structure still matches.
      expect(sharedStructure(huakangDModules)).toEqual(sharedStructure(huakangCModules.filter(module => module.id !== 'cutting')))
      expectNoForeignFactoryData(wrapper, huakangDModules, 'huakang-d', '华康D')
      if (departmentId === 'pmc-warehouse') {
        const rawMaterialModule = huakangDModules.find((module) => module.id === 'raw-material-management')
        expect(rawMaterialModule?.stats).toBe('华康D · 公共原料资料已接入')
        expect(rawMaterialModule?.metrics).toContainEqual({ label: '原料', value: '共享' })
      }

      store.setActiveFactory('huakang-c')
      await nextTick()

      const restoredHuakangCModules = moduleSnapshots(wrapper)
      expect(restoredHuakangCModules).toEqual(huakangCModules)
      expectFactoryScopedRoutes(restoredHuakangCModules, 'huakang-c')

      wrapper.unmount()
    },
  )
})
