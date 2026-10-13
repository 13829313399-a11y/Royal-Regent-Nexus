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
      position: '工程部技术员',
      confirmation_status: 'confirmed',
    },
    force_password_change: false,
  })

  return authStore
}

function mountAccountMenu(props?: { compact?: boolean; variant?: 'light' | 'obsidian' }) {
  return mount(AccountMenu, {
    props,
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

  it('keeps the light default while supporting a compact obsidian trigger', () => {
    seedUser()
    const light = mountAccountMenu()
    expect(light.get('.account-menu').attributes('data-variant')).toBe('light')
    expect(light.get('.account-menu__details').exists()).toBe(true)

    const obsidian = mountAccountMenu({ variant: 'obsidian', compact: true })
    expect(obsidian.get('.account-menu').attributes('data-variant')).toBe('obsidian')
    expect(obsidian.find('.account-menu__details').exists()).toBe(false)
    expect(obsidian.get('.account-menu__chevron').exists()).toBe(true)
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

    expect(wrapper.text()).toContain('正式组织')
    expect(wrapper.text()).toContain('华兴')
    expect(wrapper.text()).toContain('部门')
    expect(wrapper.text()).toContain('工程部')
    expect(wrapper.text()).toContain('职位')
    expect(wrapper.text()).toContain('工程部技术员')
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
        position: '工程部技术员',
        confirmation_status: 'confirmed',
      },
      force_password_change: false,
    })

    const wrapper = mountAccountMenu()

    await wrapper.get('button[aria-label="账号与头像设置"]').trigger('click')

    expect(wrapper.text()).toContain('华兴')
    expect(wrapper.text()).toContain('工程部')
    expect(wrapper.text()).toContain('工程部技术员')
    expect(wrapper.text()).not.toContain('全部厂区')
    expect(wrapper.text()).not.toContain('全部部门')
    expect(wrapper.text()).not.toContain('集团啤办员')
  })

  it('uses current IAM department and position after a transfer despite stale profile fields', async () => {
    const auth = seedUser()
    auth.applySession({ ...auth.currentUser!, identity: {
      identity_mode: 'v2', identity_version: 2, employment_epoch: 1, employment_status: 'active',
      primary_assignment: { id: 'assignment', org_unit_id: 'group-management', org_name: '集团总务', factory_id: '', department_code: 'management', official_position_title: '总务协调员', assignment_type: 'primary', is_primary: true, valid_from: '', valid_until: null, state: 'active', revision: 1, source_request_id: null },
      active_assignments_summary: [], assignments: [], primary_factory_id: '', primary_department: 'management', position: '总务协调员', server_now: '', next_transition_at: null, effective_context_key: 'new-assignment',
    } })
    const wrapper = mountAccountMenu()
    await wrapper.get('button[aria-label="账号与头像设置"]').trigger('click')
    expect(wrapper.text()).toContain('集团总务')
    expect(wrapper.text()).toContain('综合管理')
    expect(wrapper.text()).toContain('总务协调员')
    expect(wrapper.text()).not.toContain('工程部技术员')
    expect(wrapper.text()).not.toContain('华兴')
    wrapper.unmount()
  })

  it('enlarges the menu avatar in an accessible preview and closes with Escape', async () => {
    const authStore = seedUser()
    authStore.applySession({
      ...authStore.currentUser!,
      avatar_url: '/api/auth/me/avatar?v=avatar-version-1',
    })
    const wrapper = mount(AccountMenu, {
      attachTo: document.body,
      global: {
        stubs: {
          Teleport: true,
        },
      },
    })

    await wrapper.get('button[aria-label="账号与头像设置"]').trigger('click')
    const avatarButton = wrapper.get('button[aria-label="放大查看测试账号的头像"]')
    const avatarElement = avatarButton.element as HTMLButtonElement
    avatarElement.focus()
    await avatarButton.trigger('click')
    await flushPromises()

    const preview = wrapper.get('[aria-labelledby="account-avatar-preview-title"]')
    expect(preview.text()).toContain('账户头像')
    expect(preview.text()).toContain('测试账号')
    expect(preview.get('img').attributes('src')).toBe('/api/auth/me/avatar?v=avatar-version-1')
    expect(document.activeElement?.getAttribute('aria-label')).toBe('关闭头像预览')

    await preview.trigger('keydown', { key: 'Escape' })
    await flushPromises()

    expect(wrapper.find('[aria-labelledby="account-avatar-preview-title"]').exists()).toBe(false)
    expect(document.activeElement?.getAttribute('aria-label')).toBe('放大查看测试账号的头像')
    wrapper.unmount()
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

  it('ignores an avatar response belonging to the account that just signed out', async () => {
    const auth = seedUser(), old = { ...auth.currentUser! }
    let resolve!: (value: typeof old) => void
    uploadAvatarMock.mockReturnValue(new Promise(r => resolve = r))
    const wrapper = mountAccountMenu()
    await wrapper.get('button[aria-label="账号与头像设置"]').trigger('click')
    await wrapper.findAll('button').find(b => b.text().includes('个人资料与头像'))!.trigger('click')
    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [new File(['x'], 'avatar.png', { type: 'image/png' })] })
    await input.trigger('change')
    await wrapper.findAll('button').find(b => b.text().includes('保存头像'))!.trigger('click')
    auth.applySession({ ...old, id: 'next-user', username: 'next-user', display_name: '另一账号' })
    await flushPromises()
    resolve({ ...old, avatar_url: '/private-old-avatar' }); await flushPromises()
    expect(auth.currentUser?.id).toBe('next-user')
    expect(auth.currentUser?.avatar_url).not.toBe('/private-old-avatar')
    expect(wrapper.find('[aria-labelledby="avatar-profile-title"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
