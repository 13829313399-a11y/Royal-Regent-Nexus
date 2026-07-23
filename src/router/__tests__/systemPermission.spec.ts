import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = readFileSync(join(process.cwd(), 'src/router/index.ts'), 'utf8')
const policySource = readFileSync(join(process.cwd(), 'src/config/pageAccessPolicy.ts'), 'utf8')

describe('system user management routing', () => {
  it('keeps registered permission metadata while globally allowing authenticated page access', () => {
    expect(source).toMatch(/path:\s*'\/register'[\s\S]{0,260}fullPage:\s*true/)
    expect(source).toMatch(/path:\s*'\/system\/users'[\s\S]{0,420}fullPage:\s*true[\s\S]{0,260}permissions:\s*\[['"]system:user_manage['"]\][\s\S]{0,80}enforcePermissions:\s*true/)
    expect(source).toMatch(/path:\s*'\/modules\/molding-sample'[\s\S]{0,360}permissions:\s*\[['"]molding_sample:read['"],\s*['"]molding_sample:cross_factory_read['"]\]/)
    expect(source).toMatch(/path:\s*'\/modules\/molding-sample'[\s\S]{0,420}allowAuthenticatedReadOnly:\s*true/)
    expect(source).toMatch(/path:\s*'\/modules\/production\/molding-sample-tasks'[\s\S]{0,360}permissions:\s*\[['"]molding_sample:production_read['"]\]/)
    expect(source).toMatch(/path:\s*'\/modules\/pmc-warehouse\/raw-material-management'[\s\S]{0,360}permissions:\s*\[['"]molding_sample:raw_material_write['"]\]/)
    expect(source).toMatch(/path:\s*'\/modules\/sales-business\/customer-price-conversion'[\s\S]{0,360}permissions:\s*\[['"]customer_price:read['"],\s*['"]customer_price:import_internal_quote['"]\][\s\S]{0,80}enforcePermissions:\s*true/)
    expect(source).toMatch(/path:\s*'\/modules\/molding-sample'[\s\S]{0,360}enforcePermissions:\s*true/)
    expect(source).toMatch(/path:\s*'\/modules\/production\/molding-sample-tasks'[\s\S]{0,360}enforcePermissions:\s*true/)
    expect(source).toMatch(/name:\s*'forbidden'/)
    expect(source).toMatch(/authStore\.canAny\(permissions\)/)
    expect(source).toContain('shouldEnforcePagePermissions(to.meta)')
    expect(source).toContain('shouldEnforcePagePermissions(currentRoute.meta)')
    expect(source).toMatch(/path:\s*'\/forbidden'[\s\S]{0,320}shouldRedirectForbiddenPageToHome\(\)/)
    expect(policySource).toMatch(/allowAuthenticatedReadOnlyAccess:\s*true/)
    expect(policySource).toContain('meta.enforcePermissions === true')
    expect(policySource).toContain('meta.allowAuthenticatedReadOnly !== true')
    expect(source).toMatch(/path:\s*'\/system\/users\/:userId\/access'[\s\S]{0,360}permissions:\s*\[['"]system:access_manage['"]\]/)
    expect(source).toMatch(/path:\s*'\/system\/iam\/roles'[\s\S]{0,360}permissions:\s*\[['"]system:permission_catalog_read['"]\]/)
    expect(source).toMatch(/path:\s*'\/system\/iam\/permissions',[\s\S]{0,80}redirect:\s*'\/system\/iam\/roles'/)
    expect(source).toMatch(/path:\s*'\/system\/iam\/requests',[\s\S]{0,80}redirect:\s*'\/system\/iam\/roles'/)
    expect(source).toMatch(/path:\s*'\/system\/iam\/audit',[\s\S]{0,80}redirect:\s*'\/system\/iam\/roles'/)
    expect(source).not.toContain('IamPermissionCatalogView.vue')
    expect(source).not.toContain('IamAccessRequestsView.vue')
    expect(source).not.toContain('IamAuditView.vue')
    expect(source).toMatch(/window\.addEventListener\('focus', refreshAuthorizationSnapshot\)/)
  })
})
