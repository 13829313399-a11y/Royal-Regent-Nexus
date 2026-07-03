import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AccountMenu from '../AccountMenu.vue'
import { useAuthStore } from '@/stores/auth'

const routerReplace = vi.hoisted(() => vi.fn())
const logoutMock = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({
  useRouter: () => ({
    replace: routerReplace,
  }),
}))

vi.mock('@/api/auth', () => ({
  authApi: {
    logout: logoutMock,
  },
}))

function seedUser() {
  const authStore = useAuthStore()
  authStore.applySession({
    id: 'user-1',
    username: 'engineer',
    display_name: '测试账号',
    roles: ['工程部'],
    permissions: [],
    factory_scopes: ['huaxing'],
    department_scopes: ['engineering'],
    force_password_change: false,
  })

  return authStore
}

describe('AccountMenu', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    routerReplace.mockReset()
    logoutMock.mockReset()
    logoutMock.mockResolvedValue(undefined)
  })

  it('logs out the current account and returns to the login page', async () => {
    const authStore = seedUser()
    const wrapper = mount(AccountMenu)

    expect(wrapper.text()).toContain('测试账号')

    await wrapper.get('button[aria-label="退出登录"]').trigger('click')
    await flushPromises()

    expect(logoutMock).toHaveBeenCalledTimes(1)
    expect(authStore.isAuthenticated).toBe(false)
    expect(authStore.currentUser).toBeNull()
    expect(routerReplace).toHaveBeenCalledWith({
      name: 'login',
      query: { logged_out: '1' },
    })
  })

  it('still clears the local session and leaves the workspace when the logout API fails', async () => {
    logoutMock.mockRejectedValueOnce(new Error('network down'))
    const authStore = seedUser()
    const wrapper = mount(AccountMenu)

    await wrapper.get('button[aria-label="退出登录"]').trigger('click')
    await flushPromises()

    expect(authStore.isAuthenticated).toBe(false)
    expect(authStore.currentUser).toBeNull()
    expect(routerReplace).toHaveBeenCalledWith({
      name: 'login',
      query: { logged_out: '1' },
    })
  })
})
