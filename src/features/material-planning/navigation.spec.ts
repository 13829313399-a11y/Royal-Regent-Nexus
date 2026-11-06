import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useVisibleModules } from '@/composables/useVisibleModules'

const context = vi.hoisted(() => ({ allowed: true, factory: 'huakang-c' }))
vi.mock('@/stores/app', () => ({ useAppStore: () => ({
  get activeFactoryId() { return context.factory },
  get activeProductionFactory() { return { id: context.factory, shortName: '测试厂区' } },
}) }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ can: () => false,
  canAny: (codes: string[], factory: string, department: string) => context.allowed && factory === 'huakang-c' && ((codes.includes('material_plan:read') && department === 'sales-business') || ((codes.includes('material_plan:dates_read') || codes.includes('material_purchase:read')) && department === 'pmc-warehouse')),
}) }))

beforeEach(() => { context.allowed = true; context.factory = 'huakang-c' })
describe('sales material trial navigation', () => {
  it('scopes purchase preparation to its separate permission and factory', () => {
    expect(useVisibleModules('pmc-warehouse').value.find(m => m.id === 'material-purchasing')?.route).toBe('/modules/pmc-warehouse/material-purchasing?factory=huakang-c')
    context.allowed = false
    expect(useVisibleModules('pmc-warehouse').value.some(m => m.id === 'material-purchasing')).toBe(false)
    context.allowed = true; context.factory = 'huakang-a'
    expect(useVisibleModules('pmc-warehouse').value.some(m => m.id === 'material-purchasing')).toBe(false)
  })
  it('scopes the separate procurement dates entry to the factory and explicit permission', () => {
    expect(useVisibleModules('pmc-warehouse').value.find(m => m.id === 'process-material-dates')?.route).toBe('/modules/pmc-warehouse/process-material-dates?factory=huakang-c')
    context.allowed = false
    expect(useVisibleModules('pmc-warehouse').value.some(m => m.id === 'process-material-dates')).toBe(false)
    context.allowed = true; context.factory = 'huakang-a'
    expect(useVisibleModules('pmc-warehouse').value.some(m => m.id === 'process-material-dates')).toBe(false)
  })
  it('shows a factory-scoped usable entry without falsely claiming there are no records', () => {
    const module = useVisibleModules('sales-business').value.find(m => m.id === 'material-planning')
    expect(module?.route).toBe('/modules/sales-business/material-planning?factory=huakang-c')
    expect(module?.stats).toContain('待库存、在途')
    expect(module?.stats).not.toContain('暂无本厂数据')
    expect(module?.detailPage).toBe(true)
  })
  it('hides the entry without the explicit permission', () => {
    context.allowed = false
    expect(useVisibleModules('sales-business').value.some(m => m.id === 'material-planning')).toBe(false)
  })
  it.each(['huakang-a', 'huakang-d', 'huaxing'])('hides the entry at %s', factory => {
    context.factory = factory
    expect(useVisibleModules('sales-business').value.some(m => m.id === 'material-planning')).toBe(false)
  })
})
