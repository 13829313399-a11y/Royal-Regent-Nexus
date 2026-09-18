// @vitest-environment jsdom

import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { router } from '@/router'

const qcRoutes = [
  ['/modules/qc/inspection-operations', 'qc-inspection-schedule'],
  ['/modules/qc/inspection-operations/schedule-details', 'qc-inspection-schedule-details'],
  ['/modules/qc/inspection-operations/order-records', 'qc-inspection-order-records'],
  ['/modules/qc/inspection-operations/orders/new', 'qc-inspection-order-new'],
  ['/modules/qc/inspection-operations/orders/order-123', 'qc-inspection-order-detail'],
  ['/modules/qc/inspection-operations/problems', 'qc-inspection-problems'],
  ['/modules/qc/inspection-operations/reports', 'qc-inspection-reports'],
  ['/modules/qc/inspection-operations/report-renaming', 'qc-inspection-report-renaming'],
] as const

describe('QC inspection full-page routes', () => {
  it('resolves the QC carton-mark workspace with QC-scoped carton permissions', () => {
    const resolved = router.resolve('/modules/qc/carton-mark-check?factory=huaxing')

    expect(resolved.name).toBe('qc-carton-mark-check')
    expect(resolved.matched).toHaveLength(1)
    expect(resolved.meta).toMatchObject({
      fullPage: true,
      requiresAuth: true,
      enforcePermissions: true,
      permissionDepartment: 'qc',
    })
    expect(resolved.meta.permissions).toEqual(['carton_mark:read'])
  })

  it.each(qcRoutes)('resolves %s as one flat full-page route', (path, expectedName) => {
    const resolved = router.resolve(`${path}?factory=huaxing&week=2026-W33`)

    expect(resolved.name).toBe(expectedName)
    expect(resolved.matched).toHaveLength(1)
    expect(resolved.matched[0]?.children).toHaveLength(0)
    expect(resolved.meta).toMatchObject({
      fullPage: true,
      requiresAuth: true,
      enforcePermissions: true,
      allowAuthenticatedReadOnly: true,
      permissionDepartment: 'qc',
    })
    expect(resolved.meta.permissions).toEqual(['qc_inspection:read'])
  })

  it('keeps the shared workspace provider without rendering a nested RouterView', () => {
    const source = readFileSync(
      join(process.cwd(), 'src/views/QcOperationsCenterView.vue'),
      'utf8',
    )

    expect(source).toContain('provide(qcInspectionWorkspaceKey')
    expect(source).toContain('<component :is="activeSectionComponent" v-else')
    expect(source).not.toContain('RouterView')
    expect(source).toContain('返回 QC 模块中心')
    expect(source).toContain("path: '/modules/qc'")
    expect(source).toContain('query: { factory: factoryId }')
  })

  it('retires standalone add and renaming pages with safe redirects', () => {
    const add = router.resolve('/modules/qc/inspection-operations/orders/new?factory=huaxing&week=2026-W38')
    const redirect = add.matched[0]?.redirect
    expect(typeof redirect).toBe('function')
    if (typeof redirect === 'function') expect(redirect(add)).toEqual({ name: 'qc-inspection-schedule', query: { factory: 'huaxing', week: '2026-W38', add: '1' } })
    const renamed = router.resolve('/modules/qc/inspection-operations/report-renaming?factory=huaxing')
    const retired = renamed.matched[0]?.redirect
    expect(typeof retired).toBe('function')
    if (typeof retired === 'function') expect(retired(renamed)).toEqual({ name: 'qc-inspection-reports', query: { factory: 'huaxing' } })
  })
})
