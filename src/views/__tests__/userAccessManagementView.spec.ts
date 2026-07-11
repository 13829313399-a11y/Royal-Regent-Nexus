import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = readFileSync(join(process.cwd(), 'src/views/UserAccessManagementView.vue'), 'utf8')
const matrixSource = readFileSync(join(process.cwd(), 'src/components/iam/IamPermissionMatrix.vue'), 'utf8')
const identitySource = readFileSync(join(process.cwd(), 'src/components/iam/IamIdentitySummary.vue'), 'utf8')
const roleBindingsSource = readFileSync(join(process.cwd(), 'src/components/iam/IamRoleBindings.vue'), 'utf8')

describe('UserAccessManagementView contract', () => {
  it('implements scoped three-state draft, preview, and atomic commit', () => {
    for (const required of [
      'IamIdentitySummary',
      'IamScopeSelector',
      'IamRoleBindings',
      'IamPermissionMatrix',
      'inherit',
      'allow',
      'deny',
      'iamApi.getUserAccess',
      'iamApi.listPermissions',
      'iamApi.getManageableScopes',
      'iamApi.previewUserAccess',
      'base_revision',
      'reason',
      'iamApi.commitUserAccess',
      'preview_token',
      'confirmHighRisk',
      'authStore.refreshSession',
    ]) {
      expect(source).toContain(required)
    }
    expect(source).not.toContain('hasPermission(')
    expect(source).not.toContain('factoryScopes')
  })

  it('contains a narrow-screen layout contract without page-level horizontal scrolling', () => {
    expect(source).toContain('overflow-x-clip')
    expect(source).toContain('w-full min-w-0')
    expect(source).toContain('data-testid="permission-action-panel"')
    expect(source).not.toContain('xl:sticky xl:bottom-4')
    expect(source).not.toContain('xl:mb-28')
    expect(source).toContain('grid-cols-1')

    expect(matrixSource).toContain('data-testid="mobile-permission-list"')
    expect(matrixSource).toContain('md:hidden')
    expect(matrixSource).toContain('data-testid="desktop-permission-table"')
    expect(matrixSource).toContain('class="hidden overflow-x-auto')
    expect(matrixSource).toContain('md:block')
    expect(matrixSource).toContain('[overflow-wrap:anywhere]')

    expect(identitySource).toContain('[overflow-wrap:anywhere]')
    expect(identitySource).toContain('min-w-0')
    expect(identitySource).toContain("suspended: '已停用'")
    expect(identitySource).toContain("retired: '已离职'")
    expect(identitySource).toContain("pending: '待审批'")
    expect(identitySource).toContain("rejected: '已拒绝'")
    expect(identitySource).toContain("labels[status] ?? '未知状态'")
    expect(roleBindingsSource).toContain('aria-label="新增角色模板"')
  })
})
