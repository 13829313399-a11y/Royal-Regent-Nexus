import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = readFileSync(join(process.cwd(), 'src/router/index.ts'), 'utf8')

describe('system user management routing', () => {
  it('keeps business modules browseable while enforcing permission on system management', () => {
    expect(source).toMatch(/path:\s*'\/register'[\s\S]{0,260}fullPage:\s*true/)
    expect(source).toMatch(/path:\s*'\/system\/users'[\s\S]{0,420}permissions:\s*\[['"]system:user_manage['"]\][\s\S]{0,80}enforcePermissions:\s*true/)
    expect(source).toMatch(/path:\s*'\/modules\/molding-sample'[\s\S]{0,360}permissions:\s*\[['"]molding_sample:read['"]\]/)
    expect(source).toMatch(/path:\s*'\/modules\/production\/molding-sample-tasks'[\s\S]{0,360}permissions:\s*\[['"]molding_sample:production_read['"]\]/)
    expect(source).toMatch(/path:\s*'\/modules\/production\/injection-scheduling'[\s\S]{0,360}permissions:\s*\[['"]injection_schedule:read['"]\]/)
    expect(source).toMatch(/path:\s*'\/modules\/pmc-warehouse\/raw-material-management'[\s\S]{0,360}permissions:\s*\[['"]molding_sample:warehouse_requisition['"]\]/)
    expect(source).toMatch(/path:\s*'\/modules\/sales-business\/quote-center'[\s\S]{0,360}permissions:\s*\[['"]customer_price:read['"]\]/)
    expect(source).not.toMatch(/path:\s*'\/modules\/molding-sample'[\s\S]{0,360}enforcePermissions:\s*true/)
    expect(source).not.toMatch(/path:\s*'\/modules\/production\/molding-sample-tasks'[\s\S]{0,360}enforcePermissions:\s*true/)
    expect(source).toMatch(/name:\s*'forbidden'/)
    expect(source).toMatch(/authStore\.hasAnyPermission/)
    expect(source).toMatch(/const shouldEnforcePermissions = to\.meta\.enforcePermissions === true/)
    expect(source).toMatch(/if \(shouldEnforcePermissions && permissions\.length && !authStore\.hasAnyPermission\(permissions\)\)/)
    expect(source).not.toMatch(/if \(permissions\.length && !authStore\.hasAnyPermission\(permissions\)\)/)
  })
})
