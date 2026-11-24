import { writeFileSync } from 'node:fs'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { departmentModuleRegistry, factoryContexts, type ModuleDepartmentId } from '@/data/enterpriseMock'
import { useVisibleModules } from '@/composables/useVisibleModules'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { router } from '@/router'
import { routeVisualIdentity } from '../classifyNavigation'
import { resolveMotionDestination } from '../useModuleEntryMotion'

beforeEach(() => {
  setActivePinia(createPinia())
  const permissions = [...new Set(['uv_ops:read', 'spray_ops:read', 'carton_procurement:read', 'carton_mark:read',
    ...Object.values(departmentModuleRegistry).flatMap(department => department.modules.flatMap(module => module.permissions ?? []))])]
  useAuthStore().applySession({ id: 'synthetic-catalog', username: 'synthetic', display_name: 'Synthetic', roles: [], permissions, grants: [], factory_scopes: ['*'], department_scopes: ['*'], force_password_change: false,
    effective_access: [{ permission_code: 'uv_ops:read', factory_id: 'huakang-a', department: 'production', effect: 'allow', allowed: true, source_type: 'role_binding', source_ids: ['synthetic-uv'] }],
  })
  vi.stubEnv('VITE_SPRAY_OPS_ENABLED', 'true')
})
afterEach(() => vi.unstubAllEnvs())

describe('actual final catalog and registered route families', () => {
  it('accounts for every catalog appearance under every raw factory without granting routes', () => {
    const coverage: Record<string, unknown>[] = []
    const expectedModules: Record<ModuleDepartmentId, string[]> = {
      'engineering': ['molding-sample', 'bom-process', 'ecn', 'drawings', 'maintenance'],
      'pmc-warehouse': ['material-purchasing', 'process-material-dates', 'fabric-warehouse', 'material-handover', 'semi-finished-warehouse', 'carton-procurement', 'carton-supplier', 'carton-mark-check', 'raw-material-management', 'shipping-management'],
      'production': ['injection-scheduling', 'production-plan', 'three-d-printing', 'molding-sample-production-task', 'cutting', 'spray-production', 'uv-printing'],
      'qa': ['incoming-inspection', 'inspection-operations', 'quality-exception', 'quality-reports'],
      'qc': ['inspection-operations', 'carton-mark-check'],
      'sales-business': ['material-planning', 'internal-quote-desk', 'customer-price-conversion', 'indonesia-shipping', 'indonesia-material-shipment', 'po-schedule-intake'],
      'accounting': ['indonesia-invoice-reconciliation', 'mainland-invoice'],
    }
    expect(Object.keys(departmentModuleRegistry).sort()).toEqual(Object.keys(expectedModules).sort())
    let appearances = 0
    for (const department of Object.keys(departmentModuleRegistry) as ModuleDepartmentId[]) {
      const ids = departmentModuleRegistry[department].modules.map(module => module.id)
      expect([...ids].sort()).toEqual([...expectedModules[department]].sort())
      appearances += ids.length
      const visible = useVisibleModules(department)
      for (const factory of factoryContexts) {
        useAppStore().setActiveFactory(factory.id)
        for (const module of departmentModuleRegistry[department].modules) {
          const final = visible.value.find(item => item.id === module.id)
          if (!final) { coverage.push({ department, module: module.id, factory: factory.id, state: 'filtered-by-existing-catalog' }); continue }
          if (!final.route && !final.href) { coverage.push({ department, module: module.id, factory: factory.id, state: 'no-target' }); continue }
          for (const [control, raw] of [['route', final.route], ['href', final.href]] as const) {
            if (!raw) continue
            if (/^https?:\/\//.test(raw)) { coverage.push({ department, module: module.id, factory: factory.id, control, raw, state: 'external-native' }); continue }
            const target = resolveMotionDestination(router, raw)
            const identity = routeVisualIdentity(target)
            expect(target.matched.length, raw).toBeGreaterThan(0)
            expect(identity.eligible, raw).toBe(true)
            coverage.push({ department, module: module.id, title: module.title, factory: factory.id, control, raw,
              finalName: target.name, finalPath: target.path, motionIdentity: identity.id,
              surface: target.meta.fullPage ? 'business-fullpage' : 'standard',
              state: identity.home ? 'redirects-home-no-module-launch' : 'shared-host',
            })
          }
        }
      }
    }
    expect(appearances).toBe(36)
    expect(coverage.some(row => row.module === 'uv-printing' && row.factory === 'huakang-a' && row.state === 'shared-host')).toBe(true)
    expect(coverage.some(row => row.module === 'production-plan' && row.control === 'href' && row.state === 'redirects-home-no-module-launch')).toBe(true)
    if (process.env.ROUTE_MOTION_COVERAGE_OUTPUT) writeFileSync(process.env.ROUTE_MOTION_COVERAGE_OUTPUT, JSON.stringify({ source: 'actual useVisibleModules + router registry; synthetic explicit catalog read grants, not runtime permission acceptance', appearances, rows: coverage }, null, 2))
  })
  it.each([
    ['/modules/production/uv-printing/live', '/modules/production/uv-printing/planning'],
    ['/modules/production/cutting/dashboard', '/modules/production/cutting/master'],
    ['/modules/production/spray-production/overview', '/modules/production/spray-production/master'],
    ['/modules/pmc-warehouse/fabric-warehouse', '/modules/pmc-warehouse/fabric-warehouse/receipts'],
    ['/modules/sales-business/internal-quote-desk', '/modules/sales-business/internal-quote-desk/test/summary'],
  ])('%s shares its registered parent identity with %s', (a, b) => {
    const first = resolveMotionDestination(router, a), second = resolveMotionDestination(router, b)
    expect(first.matched.length).toBeGreaterThan(0)
    expect(second.matched.length).toBeGreaterThan(0)
    expect(routeVisualIdentity(first).id).toBe(routeVisualIdentity(second).id)
    expect(routeVisualIdentity(first).home).toBe(false)
  })
  it('keeps raw factory restrictions, targetless permissions and supplier remapping', () => {
    const app = useAppStore(), auth = useAuthStore(), production = useVisibleModules('production'), warehouse = useVisibleModules('pmc-warehouse')
    app.setActiveFactory('group'); expect(production.value.some(module => module.id === 'uv-printing')).toBe(false)
    app.setActiveFactory('huakang-c'); expect(production.value.some(module => module.id === 'uv-printing')).toBe(false)
    app.setActiveFactory('huakang-a'); auth.permissions = []; auth.effectiveAccess = []
    expect(production.value.find(module => module.id === 'uv-printing')?.route).toBeUndefined()
    auth.permissions = ['carton_supplier:read']
    auth.effectiveAccess = [{ permission_code: 'carton_supplier:read', factory_id: '*', department: '*', effect: 'allow', allowed: true, source_type: 'role_binding', source_ids: ['synthetic-supplier'] }]
    expect(auth.can('carton_supplier:read', '*', '*')).toBe(true)
    expect(warehouse.value.find(module => module.id === 'carton-supplier')?.route).toBe('/carton-supplier')
    expect(warehouse.value.find(module => module.id === 'carton-mark-check')?.route).toBe('/carton-supplier/carton-mark')
    auth.permissions = ['carton_procurement:read', 'carton_mark:read']
    auth.effectiveAccess = []
    expect(warehouse.value.find(module => module.id === 'carton-supplier')?.route).toContain('/modules/pmc-warehouse/carton-procurement')
  })
})
