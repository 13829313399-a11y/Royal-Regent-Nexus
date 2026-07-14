import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = readFileSync(join(process.cwd(), 'src/router/index.ts'), 'utf8')

describe('system user management routing', () => {
  it('enforces registered read permissions on business and IAM routes', () => {
    expect(source).toMatch(/path:\s*'\/register'[\s\S]{0,260}fullPage:\s*true/)
    expect(source).toMatch(/path:\s*'\/system\/users'[\s\S]{0,420}fullPage:\s*true[\s\S]{0,260}permissions:\s*\[['"]system:user_manage['"]\][\s\S]{0,80}enforcePermissions:\s*true/)
    expect(source).toMatch(/path:\s*'\/modules\/molding-sample'[\s\S]{0,360}permissions:\s*\[['"]molding_sample:read['"],\s*['"]molding_sample:cross_factory_read['"]\]/)
    expect(source).toMatch(/path:\s*'\/modules\/molding-sample'[\s\S]{0,420}allowAuthenticatedReadOnly:\s*true/)
    expect(source).toMatch(/path:\s*'\/modules\/production\/molding-sample-tasks'[\s\S]{0,360}permissions:\s*\[['"]molding_sample:production_read['"]\]/)
    expect(source).toMatch(/path:\s*'\/modules\/production\/injection-scheduling'[\s\S]{0,360}permissions:\s*\[['"]injection_schedule:read['"]\]/)
    expect(source).toMatch(/path:\s*'\/modules\/pmc-warehouse\/raw-material-management'[\s\S]{0,360}permissions:\s*\[['"]molding_sample:raw_material_write['"]\]/)
    expect(source).toMatch(/path:\s*'\/modules\/sales-business\/customer-price-conversion'[\s\S]{0,360}permissions:\s*\[['"]customer_price:read['"]\]/)
    expect(source).toMatch(/path:\s*'\/modules\/sales-business\/internal-pricing'[\s\S]{0,360}permissions:\s*\[['"]internal_pricing:read['"]\]/)
    expect(source).toMatch(/path:\s*'\/modules\/molding-sample'[\s\S]{0,360}enforcePermissions:\s*true/)
    expect(source).toMatch(/path:\s*'\/modules\/production\/molding-sample-tasks'[\s\S]{0,360}enforcePermissions:\s*true/)
    expect(source).toMatch(/path:\s*'\/modules\/production\/injection-scheduling'[\s\S]{0,360}enforcePermissions:\s*true/)
    expect(source).toMatch(/name:\s*'forbidden'/)
    expect(source).toMatch(/authStore\.canAny\(permissions\)/)
    expect(source).toMatch(/const shouldEnforcePermissions = to\.meta\.enforcePermissions === true/)
    expect(source).toMatch(/shouldEnforcePermissions[\s\S]{0,180}!allowAuthenticatedReadOnly[\s\S]{0,180}!authStore\.canAny\(permissions\)/)
    expect(source).toMatch(/path:\s*'\/system\/users\/:userId\/access'[\s\S]{0,360}permissions:\s*\[['"]system:access_manage['"]\]/)
    expect(source).toMatch(/path:\s*'\/system\/iam\/roles'[\s\S]{0,360}permissions:\s*\[['"]system:permission_catalog_read['"]\]/)
    expect(source).toMatch(/path:\s*'\/system\/iam\/permissions'[\s\S]{0,360}permissions:\s*\[['"]system:permission_catalog_read['"]\]/)
    expect(source).toMatch(/path:\s*'\/system\/iam\/requests'[\s\S]{0,360}permissions:\s*\[['"]system:access_request['"],\s*['"]system:access_approve['"]\]/)
    expect(source).toMatch(/path:\s*'\/system\/iam\/audit'[\s\S]{0,360}permissions:\s*\[['"]system:audit_read['"]\]/)
    expect(source).toMatch(/window\.addEventListener\('focus', refreshAuthorizationSnapshot\)/)
  })
})
