import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { uvPreviewRoutes, uvPrintingChildRoutes, uvPrintingRoutes } from '../routes'
import { UV_NAV } from '../navigation'
import { departmentModuleRegistry, getFactoryScopedModule } from '@/data/enterpriseMock'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

/**
 * 路由与模块目录契约（T01 / T02 / T41 的前端部分）。
 *
 * 这些断言锁定「华康A 生产部专属、其他厂区不可见、DEV 样例单独注册」这三条
 * 边界；任何把 UV 入口放宽到集团兜底或静态注册预览路由的改动都会让它们失败。
 */

const WORKSPACE_BASE = '/modules/production/uv-printing'
const PREVIEW_BASE = '/__preview/uv-printing'

describe('UV 路由注册', () => {
  it('正式工作区挂在 /modules/production/uv-printing，并使用严格华康A/生产部元信息', () => {
    expect(uvPrintingRoutes).toHaveLength(1)
    const workspace = uvPrintingRoutes[0]!
    expect(workspace.path).toBe(WORKSPACE_BASE)
    const meta = workspace.meta as Record<string, unknown>
    expect(meta.fullPage).toBe(true)
    expect(meta.requiresAuth).toBe(true)
    expect(meta.permissions).toEqual(['uv_printing:read'])
    expect(meta.enforcePermissions).toBe(true)
    expect(meta.strictPermissions).toBe(true)
    expect(meta.permissionFactoryId).toBe('huakang-a')
    expect(meta.permissionDepartment).toBe('production')
  })

  it('七个工作区子路由齐备且带标题', () => {
    const named = uvPrintingChildRoutes
      .filter((route) => typeof route.name === 'string')
      .map((route) => route.name as string)
    expect(named.sort()).toEqual([
      'uv-printing-catalog',
      'uv-printing-ink',
      'uv-printing-machines',
      'uv-printing-overview',
      'uv-printing-production',
      'uv-printing-reports',
      'uv-printing-workforce',
    ])
    for (const route of uvPrintingChildRoutes) {
      if (typeof route.name !== 'string') continue
      expect(typeof (route.meta as Record<string, unknown>).title).toBe('string')
    }
  })

  it('空路径重定向到驾驶舱并保留 query', () => {
    const redirect = uvPrintingChildRoutes[0]!.redirect as (to: { query: Record<string, unknown> }) => { path: string }
    expect(redirect({ query: { factory: 'huakang-a', date: '2026-09-13' } })).toEqual({
      path: `${WORKSPACE_BASE}/overview`,
      query: { factory: 'huakang-a', date: '2026-09-13' },
    })
  })

  it('预览路由未开启时不注册任何记录（生产包不可达）', () => {
    expect(uvPreviewRoutes(false)).toEqual([])
  })

  it('预览路由开启时带全页与登录要求，但显式不要求尚未注册的 UV 业务权限', () => {
    const routes = uvPreviewRoutes(true)
    expect(routes).toHaveLength(1)
    const preview = routes[0]!
    expect(preview.path).toBe(PREVIEW_BASE)
    const meta = preview.meta as Record<string, unknown>
    expect(meta.fullPage).toBe(true)
    expect(meta.requiresAuth).toBe(true)
    expect(meta.enforcePermissions).toBe(false)
    expect(meta.allowAuthenticatedReadOnly).toBe(true)
    expect(meta.previewOnly).toBe(true)
    // 预览不继承正式权限作用域
    expect(meta.permissionFactoryId).toBeUndefined()
    expect(meta.strictPermissions).toBeUndefined()
  })

  it('预览子路由不与正式子路由重名（避免 vue-router 名称冲突）', () => {
    const workspaceNames = new Set(
      uvPrintingChildRoutes.map((route) => route.name).filter((name): name is string => typeof name === 'string'),
    )
    const previewChildren = uvPreviewRoutes(true)[0]!.children ?? []
    for (const child of previewChildren) {
      if (typeof child.name === 'string' && child.name !== 'uv-printing-preview') {
        expect(workspaceNames.has(child.name)).toBe(false)
      }
    }
  })
})

describe('UV 二级导航', () => {
  /** 子路由里的 `machines/:id?` 对应导航里的 `machines`。 */
  const navComparable = (path: string) => path.replace(/\/:id\?$/, '')

  it('七个入口与子路由路径一一对应', () => {
    const childPaths = new Set(
      uvPrintingChildRoutes
        .map((route) => route.path)
        .filter((path) => path && path !== '')
        .map(navComparable),
    )
    expect(UV_NAV.map((entry) => entry.path).sort()).toEqual([...childPaths].sort())
    expect(UV_NAV).toHaveLength(7)
  })

  it('navigation 里 machines 入口对应带可选 id 的子路由', () => {
    const machinesRoute = uvPrintingChildRoutes.find((route) => route.name === 'uv-printing-machines')
    expect(machinesRoute?.path).toBe('machines/:id?')
    expect(UV_NAV.find((entry) => entry.key === 'machines')?.path).toBe('machines')
  })

  it('每个入口都声明描述与最低权限，且现场入口包含报工相关三项', () => {
    for (const entry of UV_NAV) {
      expect(entry.description.length).toBeGreaterThan(0)
      expect(entry.permission).toBe('uv_printing:read')
    }
    const fieldKeys = UV_NAV.filter((entry) => entry.fieldFriendly).map((entry) => entry.key)
    expect(fieldKeys).toContain('overview')
    expect(fieldKeys).toContain('production')
  })
})

describe('模块目录卡片', () => {
  const productionModules = departmentModuleRegistry.production.modules

  it('生产部注册 uv-printing，作用域为华康A + production + 严格访问', () => {
    const card = productionModules.find((module) => module.id === 'uv-printing')
    expect(card).toBeDefined()
    expect(card!.factoryIds).toEqual(['huakang-a'])
    expect(card!.permissions).toEqual(['uv_printing:read'])
    expect(card!.strictAccess).toBe(true)
    expect(card!.permissionDepartment).toBe('production')
    expect(card!.route).toBe(WORKSPACE_BASE)
  })

  it('卡片不写死动态经营值（统计必须来自接口或明确说明）', () => {
    const card = productionModules.find((module) => module.id === 'uv-printing')!
    expect(card.statusMetrics).toEqual([])
  })

  it('华康A 作用域解析后仍指向 UV 工作区，并显式带上华康A 上下文', () => {
    const card = productionModules.find((module) => module.id === 'uv-printing')!
    const scoped = getFactoryScopedModule(card, 'huakang-a')
    expect(scoped.route).toBe(`${WORKSPACE_BASE}?factory=huakang-a`)
  })

  it('未把集团兜底工厂写进 factoryIds（否则集团目录会显示 UV 卡片）', () => {
    const card = productionModules.find((module) => module.id === 'uv-printing')!
    expect(card.factoryIds).not.toContain('group')
    expect(card.factoryIds).not.toContain('huaxing')
  })
})

describe('厂区一致性守卫', () => {
  const guard = uvPrintingRoutes[0]!.beforeEnter as (to: { query: Record<string, unknown> }) => unknown
  const redirectToProduction = {
    path: '/modules/production',
    query: { factory: 'huakang-a' },
    replace: true,
  }

  beforeEach(() => {
    vi.stubEnv('VITE_UV_ENABLED', 'true')
    setActivePinia(createPinia())
  })

  it('query 指定其他厂区时改道生产部，不查询 UV 数据', () => {
    useAuthStore().isAuthenticated = false
    expect(guard({ query: { factory: 'huaxing' } })).toEqual(redirectToProduction)
  })

  it('正式开关关闭时即使华康A已登录也不进入 UV 路由', () => {
    vi.stubEnv('VITE_UV_ENABLED', 'false')
    useAuthStore().isAuthenticated = true
    useAppStore().setActiveFactory('huakang-a')
    expect(guard({ query: { factory: 'huakang-a' } })).toEqual(redirectToProduction)
  })

  it('已登录但有效厂区不是华康A 时同样改道，不静默切厂', () => {
    const authStore = useAuthStore()
    authStore.isAuthenticated = true
    const appStore = useAppStore()
    appStore.setActiveFactory('huaxing')
    expect(guard({ query: {} })).toEqual(redirectToProduction)
    appStore.setActiveFactory('group')
    expect(guard({ query: {} })).toEqual(redirectToProduction)
  })

  it('已登录且有效厂区是华康A 时放行', () => {
    const authStore = useAuthStore()
    authStore.isAuthenticated = true
    useAppStore().setActiveFactory('huakang-a')
    expect(guard({ query: { factory: 'huakang-a' } })).toBe(true)
  })

  it('未登录时不读 store，先放行给登录守卫处理', () => {
    useAuthStore().isAuthenticated = false
    useAppStore().setActiveFactory('group')
    expect(guard({ query: {} })).toBe(true)
  })

  it('数组形式的 query.factory 也按第一个值判断', () => {
    useAuthStore().isAuthenticated = false
    expect(guard({ query: { factory: ['huadeng', 'huakang-a'] } })).toEqual(redirectToProduction)
  })
})

describe('页面组件可解析', () => {
  it('七个页面都能被动态 import 解析（不存在缺失文件名）', async () => {
    const loaded = await Promise.all(
      uvPrintingChildRoutes
        .filter((route) => typeof route.name === 'string')
        .map((route) => route.component as () => Promise<unknown>),
    )
    expect(loaded).toHaveLength(7)
    for (const component of loaded) expect(component).toBeTruthy()
  })
})

// 防止误用：vitest 运行环境里不应有真实网络请求。
vi.stubGlobal('fetch', () => Promise.reject(new Error('tests must not perform real requests')))
