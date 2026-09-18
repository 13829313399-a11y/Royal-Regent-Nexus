import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick, reactive } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import DepartmentTabs from '@/components/modules/DepartmentTabs.vue'
import ModuleCard from '@/components/modules/ModuleCard.vue'
import PermissionMatrix from '@/components/modules/PermissionMatrix.vue'
import TodoQueue from '@/components/modules/TodoQueue.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import PortalHero from '@/components/portal/PortalHero.vue'
import { departmentPresentation } from '@/components/portal/portalPresentation'
import {
  departmentModuleRegistry,
  moduleDepartmentIds,
  type EnterpriseModule,
  type ModuleDepartmentId,
} from '@/data/enterpriseMock'
import {
  getPortalScope,
  resolvePortalShellAttribute,
  usesPortalRegion,
  usesPortalShell,
} from '@/lib/portalRouteScope'
import { useAppStore } from '@/stores/app'
import ModuleCenterView from '@/views/ModuleCenterView.vue'

// 必须用响应式路由对象，否则部门参数变化的用例测不到真实响应行为。
const routeState = vi.hoisted(() => ({ current: null as unknown }))
const routerPushMock = vi.hoisted(() => vi.fn())

vi.mock('vue-router', async () => {
  const { reactive } = await import('vue')
  routeState.current = reactive({
    path: '/modules/engineering',
    name: 'modules-department',
    params: { department: 'engineering' } as Record<string, string>,
    query: {} as Record<string, string>,
  })
  return {
    RouterLink: {
      name: 'RouterLink',
      props: ['to'],
      template: '<a><slot /></a>',
    },
    useRoute: () => routeState.current,
    useRouter: () => ({ push: routerPushMock }),
  }
})

interface MockRouteState {
  path: string
  name: string
  params: Record<string, string>
  query: Record<string, string>
}

const route = () => routeState.current as MockRouteState

function mountPortal() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const wrapper = mount(ModuleCenterView, { global: { plugins: [pinia] } })
  return wrapper
}

describe('portal route boundary', () => {
  it('matches every valid department route and excludes module detail routes', () => {
    for (const department of moduleDepartmentIds) {
      expect(getPortalScope({ name: 'modules-department', params: { department } })).toBe('department')
    }

    // 通用模块详情入口不能命中，否则模块内页会被换肤。
    expect(getPortalScope({ name: 'module-detail', params: { department: 'engineering', module: 'molding-sample' } })).toBeNull()
    expect(getPortalScope({ name: 'modules-department', params: { department: 'not-a-department' } })).toBeNull()
    expect(getPortalScope({ name: 'molding-sample', params: {} })).toBeNull()
    expect(getPortalScope({ name: 'login', params: {} })).toBeNull()
    expect(getPortalScope({ name: 'register', params: {} })).toBeNull()
    expect(getPortalScope({ name: undefined, params: {} })).toBeNull()
  })

  it('skins the shell only for the five ordinary-shell portal routes', () => {
    for (const name of ['dashboard', 'workbench', 'people-directory', 'shared-tool-center']) {
      const scope = getPortalScope({ name, params: {} })
      expect(usesPortalShell(scope)).toBe(true)
      expect(resolvePortalShellAttribute(scope)).toBe('jade-v3')
    }
    expect(usesPortalShell(getPortalScope({ name: 'modules-department', params: { department: 'qa' } }))).toBe(true)

    // 业务模块、模块详情与两个 fullPage 权限入口都不进入普通壳换肤。
    for (const name of ['module-detail', 'injection-scheduling', 'system-users', 'iam-role-templates', 'user-access-management']) {
      const scope = getPortalScope({ name, params: {} })
      expect(usesPortalShell(scope)).toBe(false)
      expect(resolvePortalShellAttribute(scope)).toBeUndefined()
    }
  })

  it('exposes local regions only for the three compact entries', () => {
    expect(usesPortalRegion(getPortalScope({ name: 'shared-tool-center', params: {} }), 'tools-header')).toBe(true)
    expect(usesPortalRegion(getPortalScope({ name: 'system-users', params: {} }), 'users-header')).toBe(true)
    expect(usesPortalRegion(getPortalScope({ name: 'system-users', params: {} }), 'users-stats')).toBe(true)
    expect(usesPortalRegion(getPortalScope({ name: 'iam-role-templates', params: {} }), 'roles-header')).toBe(true)
    // 用户权限职位调整页只借用了 IamNavigation，不能拿到职位页头换肤。
    expect(usesPortalRegion(getPortalScope({ name: 'user-access-management', params: {} }), 'roles-header')).toBe(false)
  })
})

describe('department presentation config', () => {
  it('covers all seven departments with distinct motifs and readable accents', () => {
    const motifs = new Set<string>()
    for (const department of moduleDepartmentIds) {
      const config = departmentPresentation[department]
      expect(config).toBeTruthy()
      expect(config.accent).toMatch(/^#[0-9A-F]{6}$/i)
      expect(config.accentSoft).toMatch(/^#[0-9A-F]{6}$/i)
      expect(config.motif.length).toBeGreaterThan(2)
      expect(config.permissionNote).toContain('目录权限示意')
      expect(config.todoEmptyText).toContain('暂无')
      motifs.add(config.motif)
    }
    // 七个部门不能共用同一种纹样，否则只是换了标题。
    expect(motifs.size).toBe(moduleDepartmentIds.length)
  })

  it('keeps accent colours distinct across departments', () => {
    const accents = moduleDepartmentIds.map((department) => departmentPresentation[department].accent.toLowerCase())
    expect(new Set(accents).size).toBe(moduleDepartmentIds.length)
  })
})

describe('portal department homepage', () => {
  beforeEach(() => {
    route().path = '/modules/engineering'
    route().name = 'modules-department'
    route().params = { department: 'engineering' }
    route().query = {}
    routerPushMock.mockReset()
  })

  it('keeps the existing PageHeader contract inside the portal identity area', () => {
    const wrapper = mountPortal()
    // 现有测试通过 PageHeader 的 title 断言厂区上下文，必须继续成立。
    const header = wrapper.getComponent(PageHeader)
    expect(wrapper.getComponent(PortalHero).exists()).toBe(true)
    expect(wrapper.find('.portal-hero').exists()).toBe(true)
    expect(wrapper.find('.portal-motif').exists()).toBe(true)

    const store = useAppStore()
    store.setActiveFactory('huakang-c')
    return nextTick().then(() => {
      expect(header.props('title')).toBe('华康C · 工程部模块中心')
      wrapper.unmount()
    })
  })

  it('applies the department presentation from the route parameter, not once on mount', async () => {
    const wrapper = mountPortal()
    const root = wrapper.get('.rrn-portal')
    expect(root.attributes('data-portal-ui')).toBe('jade-v3')
    expect(root.attributes('style')).toContain(departmentPresentation.engineering.accent)
    expect(wrapper.get('.portal-motif').attributes('data-motif')).toBe(departmentPresentation.engineering.motif)

    route().params = { department: 'accounting' }
    route().path = '/modules/accounting'
    await nextTick()

    // 同一实例在部门参数变化后必须换上新配置，而不是沿用首次挂载的值。
    expect(wrapper.get('.rrn-portal').attributes('style')).toContain(departmentPresentation.accounting.accent)
    expect(wrapper.get('.portal-motif').attributes('data-motif')).toBe(departmentPresentation.accounting.motif)
    expect(wrapper.getComponent(PageHeader).props('title')).toContain('会计部')
    wrapper.unmount()
  })

  it('renders the module grid without the legacy reveal wrapper and keeps module data intact', () => {
    const wrapper = mountPortal()
    const modules = wrapper.findAllComponents(ModuleCard)
    const registered = departmentModuleRegistry.engineering.modules
    expect(modules.length).toBeGreaterThan(0)
    expect(modules.length).toBeLessThanOrEqual(registered.length)
    // 门户接管入场动画，不与旧的 reveal-grid 叠加。
    expect(wrapper.find('.reveal-grid').exists()).toBe(false)
    expect(wrapper.find('.portal-module-grid').exists()).toBe(true)
    // 顺序与数据保持注册表原样。
    const titles = modules.map((card) => (card.props('module') as EnterpriseModule).title)
    const expected = registered
      .filter((module) => !module.factoryIds?.length || module.factoryIds.includes('huaxing'))
      .map((module) => module.title)
    expect(titles).toEqual(expected)
    wrapper.unmount()
  })

  it('marks the unrouted header action as unavailable but keeps it visible', () => {
    const wrapper = mountPortal()
    const button = wrapper.get('.portal-hero__actions [data-slot="button"]')
    expect(button.attributes('disabled')).toBeDefined()
    expect(button.text()).toContain('新增系统模块')
    expect(wrapper.get('.portal-hero__pending').text()).toContain('暂未接入')
    wrapper.unmount()
  })

  it('labels the planning meter as an illustration instead of real progress', () => {
    const wrapper = mountPortal()
    const candidates = wrapper.get('.portal-candidates')
    expect(candidates.text()).toContain('推荐下一批模块')
    expect(candidates.text()).toContain('规划示意')
    expect(candidates.text()).toContain('不代表已完成比例')
    wrapper.unmount()
  })

  it('passes the portal appearance and notes to the shared right-column components', () => {
    const wrapper = mountPortal()
    const matrix = wrapper.getComponent(PermissionMatrix)
    const todos = wrapper.getComponent(TodoQueue)
    expect(matrix.props('appearance')).toBe('portal')
    expect(matrix.props('note')).toBe(departmentPresentation.engineering.permissionNote)
    expect(todos.props('appearance')).toBe('portal')
    expect(todos.props('emptyText')).toBe(departmentPresentation.engineering.todoEmptyText)
    expect(wrapper.find('.portal-matrix').exists()).toBe(true)
    wrapper.unmount()
  })
})

describe('shared component defaults stay unchanged', () => {
  it('keeps PermissionMatrix on its original markup without the portal appearance', () => {
    const wrapper = mount(PermissionMatrix, {
      props: {
        rows: departmentModuleRegistry.accounting.permissionRows,
      },
    })
    expect(wrapper.find('.portal-matrix').exists()).toBe(false)
    expect(wrapper.find('.portal-section').exists()).toBe(false)
    expect(wrapper.find('.portal-matrix__note').exists()).toBe(false)
    expect(wrapper.get('.grid').classes()).toContain('grid-cols-[1fr_repeat(3,56px)]')
    wrapper.unmount()
  })

  it('keeps TodoQueue on its original markup without the portal appearance', () => {
    const wrapper = mount(TodoQueue, {
      props: { items: departmentModuleRegistry.engineering.todos },
    })
    expect(wrapper.find('.portal-todo').exists()).toBe(false)
    expect(wrapper.find('.portal-todo__empty').exists()).toBe(false)
    expect(wrapper.findAll('.surface-subtle').length).toBeGreaterThan(0)
    wrapper.unmount()
  })

  it('shows the compact portal empty state instead of claiming everything is done', () => {
    const wrapper = mount(TodoQueue, {
      props: {
        items: [],
        appearance: 'portal',
        emptyText: departmentPresentation.engineering.todoEmptyText,
      },
    })
    const empty = wrapper.get('.portal-todo__empty')
    expect(empty.text()).toContain('当前暂无可展示的本厂待办')
    expect(empty.text()).not.toContain('全部完成')
    wrapper.unmount()
  })
})

describe('department tabs navigation', () => {
  beforeEach(() => {
    route().path = '/modules/engineering'
    route().name = 'modules-department'
    route().params = { department: 'engineering' }
    route().query = { factory: 'huaxing' }
    routerPushMock.mockReset()
  })

  it('keeps seven route navigations and marks the current one for assistive tech', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useAppStore()
    store.setActiveFactory('huaxing')

    const wrapper = mount(DepartmentTabs, { global: { plugins: [pinia] } })
    const tabs = wrapper.findAll('[data-department-id]')
    expect(tabs).toHaveLength(7)
    const current = wrapper.findAll('[data-portal-current="true"]')
    expect(current).toHaveLength(1)
    expect(current[0]!.attributes('data-department-id')).toBe('engineering')
    expect(current[0]!.attributes('aria-current')).toBe('page')
    // 路由导航而不是不完整的 tablist 语义。
    expect(wrapper.find('[role="tablist"]').exists()).toBe(false)
    expect(wrapper.find('[role="tab"]').exists()).toBe(false)

    await tabs[2]!.trigger('click')
    expect(routerPushMock).toHaveBeenCalledTimes(1)
    const pushed = routerPushMock.mock.calls[0]![0] as { path: string; query: Record<string, string> }
    expect(pushed.path).toBe('/modules/production')
    // 切换部门保留厂区与其他查询参数，厂区来源仍是当前 store 上下文。
    expect(pushed.query.factory).toBe(store.activeFactoryId)
    expect(pushed.query.factory).toBe('huaxing')
    wrapper.unmount()
  })

  it('keeps the sliding indicator purely decorative', () => {
    setActivePinia(createPinia())
    const wrapper = mount(DepartmentTabs)
    const indicator = wrapper.get('.portal-tabs__indicator')
    expect(indicator.attributes('aria-hidden')).toBe('true')
    // 路由是状态来源，指示层不参与状态表达。
    expect(indicator.attributes('data-ready')).toBe('false')
    wrapper.unmount()
  })
})

describe('module card navigation contract', () => {
  const routedModule = departmentModuleRegistry.accounting.modules[0]!

  beforeEach(() => {
    routerPushMock.mockReset()
    setActivePinia(createPinia())
  })

  it('exposes the card as a link only when it has a route target', async () => {
    const wrapper = mount(ModuleCard, { props: { module: routedModule, index: 0 } })
    expect(wrapper.attributes('role')).toBe('link')
    expect(wrapper.attributes('tabindex')).toBe('0')
    expect(wrapper.attributes('data-navigable')).toBe('true')
    expect(wrapper.attributes('style')).toContain('--portal-card-index')

    await wrapper.trigger('keydown', { key: 'Enter' })
    expect(routerPushMock).toHaveBeenCalledTimes(1)
    expect(routerPushMock.mock.calls[0]![0]).toBe(routedModule.route)
    wrapper.unmount()
  })

  it('does not present a fake link for a card without a route', () => {
    const displayOnly = { ...routedModule, id: 'display-only', route: undefined, href: undefined }
    const wrapper = mount(ModuleCard, { props: { module: displayOnly } })
    expect(wrapper.attributes('role')).toBeUndefined()
    expect(wrapper.attributes('tabindex')).toBeUndefined()
    expect(wrapper.attributes('data-navigable')).toBe('false')
    expect(wrapper.find('.portal-action').exists()).toBe(false)
    wrapper.unmount()
  })

  it('does not navigate twice when the key event comes from an inner link', async () => {
    const wrapper = mount(ModuleCard, { props: { module: routedModule } })
    const innerLink = wrapper.get('.portal-action--primary')
    await innerLink.trigger('keydown', { key: 'Enter' })
    // 内部链接会冒泡 keydown；卡片必须忽略不是发生在自己身上的按键。
    expect(routerPushMock).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('hides the metric band when a module has no status metrics', () => {
    const withoutMetrics = { ...routedModule, id: 'no-metrics', statusMetrics: [] }
    const wrapper = mount(ModuleCard, { props: { module: withoutMetrics } })
    expect(wrapper.find('.portal-module-card__metrics').exists()).toBe(false)
    wrapper.unmount()
  })
})
