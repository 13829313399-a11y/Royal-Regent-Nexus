import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const source = readFileSync(join(process.cwd(), 'src/views/SystemUserManagementView.vue'), 'utf8')

describe('SystemUserManagementView source contract', () => {
  it('loads pending requests, users, roles, and submits approval assignments', () => {
    for (const requiredSource of [
      'systemApi.listRegistrationRequests',
      'systemApi.listUsers',
      'systemApi.listRoles',
      'systemApi.approveRegistrationRequest',
      'systemApi.rejectRegistrationRequest',
      'systemApi.updateUserStatus',
      'role_assignments',
      'recommended_role_ids',
      '待审批',
      '用户列表',
      '停用',
      '恢复',
    ]) {
      expect(source).toContain(requiredSource)
    }
  })
})
