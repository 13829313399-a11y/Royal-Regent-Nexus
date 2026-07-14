import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AccountMenu from '../AccountMenu.vue'
import { useAuthStore } from '@/stores/auth'

const routerReplace = vi.hoisted(() => vi.fn())
const logoutMock = vi.hoisted(() => vi.fn())
const uploadAvatarMock = vi.hoisted(() => vi.fn())
const deleteAvatarMock = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({
  useRouter: () => ({
    replace: routerReplace,
  }),
}))

vi.mock('@/api/auth', () => ({
  authApi: {
    logout: logoutMock,
    uploadAvatar: uploadAvatarMock,
    deleteAvatar: deleteAvatarMock,
  },
}))

function seedUser() {
  const authStore = useAuthStore()
  authStore.applySession({
    id: 'user-1',
    username: 'engineer',
    display_name: '测试账号',
    roles: ['工程师'],
    permissions: [],
    grants: [],
    factory_scopes: ['huaxing'],
    department_scopes: ['engineering'],
    profile: {
      primary_factory_id: 'huaxing',
      primary_department: 'engineering',
      position: '工程师',
      confirmation_status: 'confirmed',
    },
    force_password_change: false,
  })

  return authStore
}

function mountAccountMenu() {
  return mount(AccountMenu, {
    global: {
      stubs: {
        Teleport: true,
      },
    },
  })
}

describe('AccountMenu', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    routerReplace.mockReset()
    logoutMock.mockReset()
    logoutMock.mockResolvedValue(undefined)
    uploadAvatarMock.mockReset()
    deleteAvatarMock.mockReset()
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => 'blob:avatar-preview'),
      revokeObjectURL: vi.fn(),
    })
  })

  it('logs out the current account and returns to the login page', async () => {
    const authStore = seedUser()
    const wrapper = mountAccountMenu()

    expect(wrapper.text()).toContain('测试账号')

    await wrapper.get('button[aria-label="账号与头像设置"]').trigger('click')
    const logoutButton = wrapper.findAll('button').find((button) => button.text().includes('退出登录'))
    expect(logoutButton).toBeDefined()
    await logoutButton!.trigger('click')
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
    const wrapper = mountAccountMenu()

    await wrapper.get('button[aria-label="账号与头像设置"]').trigger('click')
    const logoutButton = wrapper.findAll('button').find((button) => button.text().includes('退出登录'))
    expect(logoutButton).toBeDefined()
    await logoutButton!.trigger('click')
    await flushPromises()

    expect(authStore.isAuthenticated).toBe(false)
    expect(authStore.currentUser).toBeNull()
    expect(routerReplace).toHaveBeenCalledWith({
      name: 'login',
      query: { logged_out: '1' },
    })
  })

  it('shows the factory, department, and position from the registered profile', async () => {
    seedUser()
    const wrapper = mountAccountMenu()

    await wrapper.get('button[aria-label="账号与头像设置"]').trigger('click')

    expect(wrapper.text()).toContain('厂区')
    expect(wrapper.text()).toContain('华兴')
    expect(wrapper.text()).toContain('部门')
    expect(wrapper.text()).toContain('工程部')
    expect(wrapper.text()).toContain('职位')
    expect(wrapper.text()).toContain('工程师')
  })

  it('does not show authorization scopes or role bindings as registered profile data', async () => {
    const authStore = useAuthStore()
    authStore.applySession({
      id: 'user-admin',
      username: 'admin',
      display_name: '测试工程师',
      roles: ['系统管理员', '集团啤办员'],
      permissions: ['system:user_manage'],
      grants: [],
      factory_scopes: ['*'],
      department_scopes: ['*'],
      profile: {
        primary_factory_id: 'huaxing',
        primary_department: 'engineering',
        position: '工程师',
        confirmation_status: 'confirmed',
      },
      force_password_change: false,
    })

    const wrapper = mountAccountMenu()

    await wrapper.get('button[aria-label="账号与头像设置"]').trigger('click')

    expect(wrapper.text()).toContain('华兴')
    expect(wrapper.text()).toContain('工程部')
    expect(wrapper.text()).toContain('工程师')
    expect(wrapper.text()).not.toContain('全部厂区')
    expect(wrapper.text()).not.toContain('全部部门')
    expect(wrapper.text()).not.toContain('集团啤办员')
  })

  it('opens a formal avatar dialog and applies the returned current-user profile', async () => {
    const authStore = seedUser()
    uploadAvatarMock.mockResolvedValue({
      ...authStore.currentUser,
      avatar_url: '/api/auth/me/avatar?v=avatar-version-1',
    })
    const wrapper = mountAccountMenu()

    await wrapper.get('button[aria-label="账号与头像设置"]').trigger('click')
    const profileButton = wrapper.findAll('button').find((button) => button.text().includes('个人资料与头像'))
    expect(profileButton).toBeDefined()
    await profileButton!.trigger('click')

    expect(wrapper.get('[role="dialog"]').text()).toContain('个人资料与头像')
    expect(wrapper.get('[role="dialog"]').text()).toContain('支持 JPG、PNG、WebP')

    const file = new File(['avatar-content'], 'avatar.png', { type: 'image/png' })
    const fileInput = wrapper.get('input[type="file"]')
    Object.defineProperty(fileInput.element, 'files', {
      configurable: true,
      value: [file],
    })
    await fileInput.trigger('change')
    const saveButton = wrapper.findAll('button').find((button) => button.text().includes('保存头像'))
    expect(saveButton).toBeDefined()
    await saveButton!.trigger('click')
    await flushPromises()

    expect(uploadAvatarMock).toHaveBeenCalledWith(file)
    expect(authStore.currentUser?.avatar_url).toBe('/api/auth/me/avatar?v=avatar-version-1')
    expect(wrapper.get('[role="dialog"]').text()).toContain('头像已保存')
  })
})
