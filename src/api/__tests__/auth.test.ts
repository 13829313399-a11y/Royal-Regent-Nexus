import assert from 'node:assert/strict'
import { createAuthApi } from '../auth.js'

const calls: Array<{ method: string, url: string, data?: unknown }> = []

const client = {
  async get(url: string) {
    calls.push({ method: 'get', url })
    return { data: { url } }
  },
  async post(url: string, data?: unknown) {
    calls.push({ method: 'post', url, data })
    return { data: { url, data } }
  },
}

const api = createAuthApi(client as Parameters<typeof createAuthApi>[0])

await api.login({ username: 'engineer', password: '123456' })
await api.getMe()
await api.changePassword({
  current_password: 'temporary-password',
  new_password: 'FormalPass456!',
  confirm_password: 'FormalPass456!',
})
await api.logout()

assert.deepEqual(calls.map((call) => `${call.method} ${call.url}`), [
  'post /auth/login',
  'get /auth/me',
  'post /auth/change-password',
  'post /auth/logout',
])
assert.deepEqual(calls[0].data, { username: 'engineer', password: '123456' })
assert.deepEqual(calls[2].data, {
  current_password: 'temporary-password',
  new_password: 'FormalPass456!',
  confirm_password: 'FormalPass456!',
})
