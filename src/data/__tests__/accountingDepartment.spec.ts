import { describe, expect, it } from 'vitest'
import {
  departmentModuleRegistry,
  departments,
  getDepartmentRoute,
  isModuleDepartmentId,
  navigationGroups,
} from '@/data/enterpriseMock'

describe('accounting department navigation', () => {
  it('registers 会计部 as a public department module with a working entry route', () => {
    expect(isModuleDepartmentId('accounting')).toBe(true)
    expect(departments).toContainEqual(expect.objectContaining({
      id: 'accounting',
      name: '会计部',
    }))

    const mainNavigation = navigationGroups.find((group) => group.label === 'MAIN')
    expect(mainNavigation?.items).toContainEqual(expect.objectContaining({
      label: '会计部',
      departmentId: 'accounting',
      to: getDepartmentRoute('accounting'),
    }))

    expect(departmentModuleRegistry.accounting).toEqual(expect.objectContaining({
      departmentId: 'accounting',
      panelTitle: '会计部模块',
    }))
    expect(departmentModuleRegistry.accounting.modules).toContainEqual(expect.objectContaining({
      id: 'indonesia-invoice-reconciliation',
      title: '印尼票据核对',
      route: '/modules/accounting/indonesia-invoice-reconciliation',
    }))
  })
})
