import { describe, expect, it } from 'vitest'
import { createSystemApi } from '../system'

describe('systemApi', () => {
  it('uses the system namespace for notifications, registration approvals, users, and roles', async () => {
    const calls: Array<{ method: string; url: string; data?: unknown }> = []
    const client = {
      async get<T = unknown>(url: string): Promise<{ data: T }> {
        calls.push({ method: 'get', url })
        return { data: { url } as T }
      },
      async post<T = unknown>(url: string, data?: unknown): Promise<{ data: T }> {
        calls.push({ method: 'post', url, data })
        return { data: { url, data } as T }
      },
      async patch<T = unknown>(url: string, data?: unknown): Promise<{ data: T }> {
        calls.push({ method: 'patch', url, data })
        return { data: { url, data } as T }
      },
    }
    const api = createSystemApi(client)

    await api.listNotifications()
    await api.listNotifications({ changed_after: '2026-07-22T08:25:00.000Z' })
    await api.updateNotification('notice-1', { status: 'handled' })
    await api.listPasswordResetRequests('pending')
    await api.getPasswordResetRequest('password-reset-1')
    await api.approvePasswordResetRequest('password-reset-1', { review_comment: '已核验' })
    await api.rejectPasswordResetRequest('password-reset-2', { review_comment: '无法核验' })
    await api.reissuePasswordResetRequest('password-reset-3', { review_comment: '重新核验' })
    await api.listRegistrationRequests('pending')
    await api.approveRegistrationRequest('registration-1', {
      system_position_role_id: 'engineer',
      profile: {
        display_name: '张三',
        phone: '13800000000',
        email: '',
        factory_id: 'huaxing',
        department: 'engineering',
        position: '工程部技术员',
      },
      review_comment: '资料完整',
    })
    await api.rejectRegistrationRequest('registration-2', { review_comment: '资料不完整' })
    await api.listUsers('active')
    await api.updateUserStatus('user-1', { status: 'suspended' })
    await api.listRoles()
    await api.listSystemPositions()

    expect(calls.map((call) => `${call.method} ${call.url}`)).toEqual([
      'get /system/notifications',
      'get /system/notifications?changed_after=2026-07-22T08%3A25%3A00.000Z',
      'patch /system/notifications/notice-1',
      'get /system/password-reset-requests?status=pending',
      'get /system/password-reset-requests/password-reset-1',
      'post /system/password-reset-requests/password-reset-1/approve',
      'post /system/password-reset-requests/password-reset-2/reject',
      'post /system/password-reset-requests/password-reset-3/reissue',
      'get /system/registration-requests?status=pending',
      'post /system/registration-requests/registration-1/approve',
      'post /system/registration-requests/registration-2/reject',
      'get /system/users?status=active',
      'patch /system/users/user-1/status',
      'get /system/roles',
      'get /system/positions',
    ])
    expect(calls[9].data).toEqual({
      system_position_role_id: 'engineer',
      profile: {
        display_name: '张三',
        phone: '13800000000',
        email: '',
        factory_id: 'huaxing',
        department: 'engineering',
        position: '工程部技术员',
      },
      review_comment: '资料完整',
    })
    expect(calls[5].data).toEqual({ review_comment: '已核验' })
  })
})
