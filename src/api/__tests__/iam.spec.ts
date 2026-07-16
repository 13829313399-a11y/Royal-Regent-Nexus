import { describe, expect, it } from 'vitest'
import { createIamApi } from '@/api/iam'

describe('iamApi', () => {
  it('uses the IAM contracts for user access and built-in position templates', async () => {
    const calls: Array<{ method: string; url: string; data?: unknown }> = []
    const client = {
      async get<T = unknown>(url: string): Promise<{ data: T }> {
        calls.push({ method: 'get', url })
        return { data: [] as T }
      },
      async post<T = unknown>(url: string, data?: unknown): Promise<{ data: T }> {
        calls.push({ method: 'post', url, data })
        return { data: { preview_token: 'preview-1' } as T }
      },
    }
    const api = createIamApi(client)

    await api.listPermissions()
    await api.getManageableScopes()
    await api.searchUsers('张三', 'active')
    await api.getUserAccess('user/1')
    await api.previewUserAccess('user/1', {
      base_revision: 3,
      reason: '开放设备维修模块',
      overrides: [{
        permission_code: 'maintenance:update',
        effect: 'allow',
        factory_id: 'huaxing',
        department: 'engineering',
        valid_until: null,
      }],
    })
    await api.commitUserAccess('user/1', 'preview-1', true)
    await api.previewUserSystemPosition('user/1', {
      base_revision: 3,
      system_position_role_id: 'engineering_supervisor',
      reason: '岗位调整',
    })
    await api.commitUserSystemPosition('user/1', 'position-preview', false)
    await api.listRoles()
    await api.listSystemPositions()
    await api.getRoleAccess('engineer')
    await api.previewRoleAccess('engineer', {
      base_version: 2,
      reason: '角色补充查看权限',
      permission_codes: ['maintenance:read'],
    })
    await api.commitRoleAccess('engineer', 'role-preview', false)
    expect(calls.map((call) => `${call.method} ${call.url}`)).toEqual([
      'get /iam/permissions?status=active',
      'get /iam/manageable-scopes',
      'get /iam/users/search?query=%E5%BC%A0%E4%B8%89&status=active',
      'get /iam/users/user%2F1/access',
      'post /iam/users/user%2F1/access/preview',
      'post /iam/users/user%2F1/access/commit',
      'post /iam/users/user%2F1/system-position/preview',
      'post /iam/users/user%2F1/system-position/commit',
      'get /iam/roles',
      'get /iam/system-positions',
      'get /iam/roles/engineer/access',
      'post /iam/roles/engineer/access/preview',
      'post /iam/roles/engineer/access/commit',
    ])
    expect(calls[4].data).toEqual({
      base_revision: 3,
      reason: '开放设备维修模块',
      overrides: [{
        permission_code: 'maintenance:update',
        effect: 'allow',
        factory_id: 'huaxing',
        department: 'engineering',
        valid_until: null,
      }],
    })
    expect(calls[5].data).toEqual({ preview_token: 'preview-1', confirm_high_risk: true })
    expect(calls[6].data).toEqual({
      base_revision: 3,
      system_position_role_id: 'engineering_supervisor',
      reason: '岗位调整',
    })
    expect(calls[7].data).toEqual({ preview_token: 'position-preview', confirm_high_risk: false })
  })
})
