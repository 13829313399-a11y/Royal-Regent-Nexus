import { describe, expect, it } from 'vitest'
import type { RouteLocationNormalizedLoaded } from 'vue-router'
import {
  buildAIPageContext,
  isAIBusinessRoute,
  supportsAIVisionContext,
} from '../pageContext'

type ContextRoute = Pick<RouteLocationNormalizedLoaded, 'name' | 'path' | 'query'>
type BusinessRoute = Pick<RouteLocationNormalizedLoaded, 'name' | 'path' | 'meta'>

function contextRoute(overrides: Partial<ContextRoute> = {}): ContextRoute {
  return {
    name: 'injection-scheduling-v2',
    path: '/modules/production/injection-scheduling',
    query: {},
    ...overrides,
  }
}

function businessRoute(name: string, path: string, requiresAuth = true): BusinessRoute {
  return { name, path, meta: { requiresAuth } }
}

describe('AI allowlisted page context', () => {
  it('constructs only the exact B4 schema and prefers the current route factory', () => {
    expect(buildAIPageContext(
      contextRoute({ query: { factory: 'huakang-b', ignored: 'never-forwarded' } }),
      'huaxing',
    )).toEqual({
      route_name: 'injection-scheduling-v2',
      path: '/modules/production/injection-scheduling',
      factory_id: 'huakang-b',
      module_id: 'injection-scheduling',
      selected_entity: null,
    })
  })

  it('drops group or forged factories and returns null outside the allowlisted route', () => {
    expect(buildAIPageContext(contextRoute({ query: { factory: 'group' } }), 'group')?.factory_id).toBeNull()
    expect(buildAIPageContext(contextRoute({ query: { factory: 'forged' } }), 'forged')?.factory_id).toBeNull()
    expect(buildAIPageContext(contextRoute({ name: 'module-detail' }), 'huaxing')).toBeNull()
    expect(buildAIPageContext(contextRoute({ path: '/modules/production/other' }), 'huaxing')).toBeNull()
  })

  it('adds only the internal quote home as a text-only B9 context', () => {
    const context = buildAIPageContext(contextRoute({
      name: 'internal-quote-desk-home',
      path: '/modules/sales-business/internal-quote-desk',
      query: { factory: 'huakang-b' },
    }), 'huaxing')

    expect(context).toEqual({
      route_name: 'internal-quote-desk-home',
      path: '/modules/sales-business/internal-quote-desk',
      factory_id: 'huakang-b',
      module_id: 'internal-quote',
      selected_entity: null,
    })
    expect(supportsAIVisionContext(context)).toBe(false)
    expect(supportsAIVisionContext(buildAIPageContext(contextRoute(), 'huaxing'))).toBe(true)
    expect(buildAIPageContext(contextRoute({
      name: 'internal-quote-collaboration',
      path: '/modules/sales-business/internal-quote-desk/IQ-1/collaboration',
    }), 'huaxing')).toBeNull()
  })

  it('allows authenticated business surfaces but excludes public, password and system pages', () => {
    expect(isAIBusinessRoute(businessRoute('dashboard', '/'))).toBe(true)
    expect(isAIBusinessRoute(businessRoute('injection-scheduling-v2', '/modules/production/injection-scheduling'))).toBe(true)
    expect(isAIBusinessRoute(businessRoute('login', '/login', false))).toBe(false)
    expect(isAIBusinessRoute(businessRoute('register', '/register', false))).toBe(false)
    expect(isAIBusinessRoute(businessRoute('change-password', '/change-password'))).toBe(false)
    expect(isAIBusinessRoute(businessRoute('forbidden', '/forbidden'))).toBe(false)
    expect(isAIBusinessRoute(businessRoute('system-users', '/system/users'))).toBe(false)
  })
})
