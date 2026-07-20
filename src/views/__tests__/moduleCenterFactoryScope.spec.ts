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
      expect(huakangCModules).toHaveLength(departmentModuleRegistry[departmentId].modules.length)
      expect(huakangCModules.map(({ id, title, childLabels }) => ({ id, title, childLabels }))).toEqual(
        departmentModuleRegistry[departmentId].modules.map((module) => ({
          id: module.id,
          title: module.title,
          childLabels: module.children.map((child) => child.label),
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
      expect(sharedStructure(huakangDModules)).toEqual(sharedStructure(huakangCModules))
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
