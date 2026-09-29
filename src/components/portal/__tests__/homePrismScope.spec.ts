import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { getHomeExperienceScope } from '@/lib/portalRouteScope'
import { moduleDepartmentIds } from '@/data/enterpriseMock'
import { homePrismPresentation } from '../homePrismPresentation'

describe('Prism V4 scope and department identities', () => {
  it('opts in precisely the dashboard and all seven valid departments', () => {
    expect(getHomeExperienceScope({ name: 'dashboard', params: {} })).toBe('dashboard')
    for (const department of moduleDepartmentIds) expect(getHomeExperienceScope({ name: 'modules-department', params: { department } })).toBe('department')
    expect(getHomeExperienceScope({ name: 'modules-department', params: { department: 'bogus' } })).toBeNull()
    expect(getHomeExperienceScope({ name: 'modules-department', params: { department: ['engineering'] } })).toBeNull()
  })
  it('excludes every protected entry regardless of department parameters', () => {
    for (const name of ['module-detail', 'molding-sample', 'injection-scheduling', 'uv-operations-live', 'three-d-printing', 'workbench', 'people-directory', 'shared-tool-center', 'system-users', 'iam-role-templates', 'user-access-management', 'login', 'register']) expect(getHomeExperienceScope({ name, params: { department: 'engineering' } })).toBeNull()
  })
  it('provides distinct department palettes without storing business catalog data', () => {
    expect(new Set(moduleDepartmentIds.map(id => homePrismPresentation[id].accent)).size).toBe(7)
    for (const value of Object.values(homePrismPresentation)) expect(Object.keys(value).sort()).toEqual(['accent', 'icon', 'light', 'soft'])
  })
  it('namespaces all normal V4 CSS selectors and leaves existing default styles intact', () => {
    for (const file of ['home-prism.css', 'home-prism-motion.css', 'home-prism-shell.css']) {
      const source = readFileSync(`src/components/portal/styles/${file}`, 'utf8').replace(/\/\*[\s\S]*?\*\//g, '')
      for (const line of source.split('\n').map(line => line.trim()).filter(line => line.startsWith('.'))) {
        expect(line.startsWith(file === 'home-prism-shell.css' ? ".app-shell[data-home-experience='prism-v4']" : ".rrn-home[data-home-experience='prism-v4']")).toBe(true)
      }
      expect(source).not.toMatch(/(?:^|\n)\s*(?:body|:root|button|h1)\s*[{,]/)
    }
  })
})
