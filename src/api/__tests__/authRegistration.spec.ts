import { describe, expect, it } from 'vitest'
import { createAuthApi } from '../auth'

describe('authApi registration', () => {
  it('posts public registration requests to the auth namespace', async () => {
    const calls: Array<{ method: string; url: string; data?: unknown }> = []
    const client = {
      async get<T = unknown>(url: string): Promise<{ data: T }> {
        calls.push({ method: 'get', url })
        return { data: { url } as T }
      },
      async post<T = unknown>(url: string, data?: unknown): Promise<{ data: T }> {
        calls.push({ method: 'post', url, data })
        return { data: { status: 'pending', message: '账号申请已提交，请等待管理员审批' } as T }
      },
    }
    const api = createAuthApi(client)

    const response = await api.register({
      username: 'zhangsan',
      display_name: '张三',
      password: 'Strong123',
      confirm_password: 'Strong123',
      phone: '13800000000',
      email: '',
      factory_id: 'huaxing',
      department: 'engineering',
      position: '工程师',
    })

    expect(calls).toEqual([
      {
        method: 'post',
        url: '/auth/register',
        data: {
          username: 'zhangsan',
          display_name: '张三',
          password: 'Strong123',
          confirm_password: 'Strong123',
          phone: '13800000000',
          email: '',
          factory_id: 'huaxing',
          department: 'engineering',
          position: '工程师',
        },
      },
    ])
    expect(response.status).toBe('pending')
  })

  it('posts public password reset requests to the auth namespace', async () => {
    const calls: Array<{ method: string; url: string; data?: unknown }> = []
    const client = {
      async get<T = unknown>(url: string): Promise<{ data: T }> {
        calls.push({ method: 'get', url })
        return { data: { url } as T }
      },
      async post<T = unknown>(url: string, data?: unknown): Promise<{ data: T }> {
        calls.push({ method: 'post', url, data })
        return { data: { status: 'submitted', message: '密码重置申请已提交，请等待管理员核验处理' } as T }
      },
    }
    const api = createAuthApi(client)

    const response = await api.requestPasswordReset({
      username: 'zhangsan',
      display_name: '张三',
      contact: '13800000000',
      note: '忘记密码',
    })

    expect(calls).toEqual([
      {
        method: 'post',
        url: '/auth/password-reset-requests',
        data: {
          username: 'zhangsan',
          display_name: '张三',
          contact: '13800000000',
          note: '忘记密码',
        },
      },
    ])
    expect(response.status).toBe('submitted')
  })
})
