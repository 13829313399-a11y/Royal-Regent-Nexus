import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import AvatarPreviewDialog from '@/components/directory/AvatarPreviewDialog.vue'
import MemberDirectoryDrawer from '@/components/directory/MemberDirectoryDrawer.vue'
import MemberDirectoryEntry from '@/components/directory/MemberDirectoryEntry.vue'
import MemberRow from '@/components/directory/MemberRow.vue'
import { useAuthStore } from '@/stores/auth'
import type { DirectoryMember } from '@/api/directory'

const apiMocks = vi.hoisted(() => ({
  getSummary: vi.fn(),
  getMembers: vi.fn(),
  sendHeartbeat: vi.fn(),
}))

vi.mock('@/api/directory', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/api/directory')>(),
  directoryApi: apiMocks,
}))

const onlineMember: DirectoryMember = {
  id: 'member-1',
  display_name: '测试成员',
  position: '工程师',
  primary_factory_id: 'huakang-a',
  primary_department: 'engineering',
  avatar_url: '/api/directory/members/member-1/avatar?v=1',
  avatar_version: '1',
  presence_state: 'online',
}

function membersResponse() {
  return {
    items: [onlineMember],
    total: 1,
    page: 1,
    page_size: 50,
    total_pages: 1,
    state_counts: { online: 1, away: 0, offline: 0 },
  }
}

describe('member directory experience', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    useAuthStore().applySession({ id: 'viewer', username: 'viewer', display_name: '查看者', roles: [], permissions: [], grants: [], factory_scopes: [], department_scopes: [], force_password_change: false, profile: { primary_factory_id: 'huakang-a', primary_department: 'engineering', position: '工程师', confirmation_status: 'confirmed' } })
    vi.useFakeTimers()
    apiMocks.getSummary.mockReset().mockResolvedValue({
      total_members: 2,
      state_counts: { online: 1, away: 0, offline: 1 },
      preview_members: [onlineMember],
    })
    apiMocks.getMembers.mockReset().mockResolvedValue(membersResponse())
    document.body.innerHTML = ''
  })

  afterEach(() => {
    vi.runOnlyPendingTimers()
    vi.useRealTimers()
    document.body.innerHTML = ''
  })

  it('renders the global summary entry and opens the organization drawer', async () => {
    const wrapper = mount(MemberDirectoryEntry, {
      props: { currentFactoryId: 'huakang-a', currentDepartment: 'engineering' },
      global: {
        stubs: { RouterLink: { template: '<a><slot /></a>' } },
      },
    })
    await flushPromises()

    expect(wrapper.get('button').text()).toContain('成员目录')
    expect(wrapper.get('button').text()).toContain('1 位在线')
    expect(wrapper.get('button').attributes('aria-label')).toBe('打开组织成员目录，1 人在线，共 2 人')
    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(document.body.textContent).toContain('成员目录')
    expect(document.body.textContent).toContain('测试成员')
    wrapper.unmount()
  })

  it('debounces search for 250ms and applies presence and current-scope filters', async () => {
    const wrapper = mount(MemberDirectoryDrawer, {
      props: {
        open: true,
        currentFactoryId: 'huakang-a',
        currentDepartment: 'engineering',
      },
      attachTo: document.body,
      global: {
        stubs: { RouterLink: { template: '<a><slot /></a>' } },
      },
    })
    await flushPromises()
    expect(apiMocks.getMembers).toHaveBeenCalledTimes(1)

    const search = document.body.querySelector<HTMLInputElement>('input[type="search"]')!
    search.value = '测试'
    search.dispatchEvent(new Event('input', { bubbles: true }))
    await nextTick()
    vi.advanceTimersByTime(249)
    await nextTick()
    expect(apiMocks.getMembers).toHaveBeenCalledTimes(1)
    vi.advanceTimersByTime(1)
    await flushPromises()
    expect(apiMocks.getMembers).toHaveBeenLastCalledWith(expect.objectContaining({ q: '测试' }), expect.any(AbortSignal))

    const presence = document.body.querySelector<HTMLSelectElement>('select[aria-label="连接状态"]')!
    presence.value = 'online'; presence.dispatchEvent(new Event('change', { bubbles: true }))
    await flushPromises()
    expect(apiMocks.getMembers).toHaveBeenLastCalledWith(expect.objectContaining({ presence: 'online', org_unit_id: 'huakang-a' }), expect.any(AbortSignal))
    const scope = document.body.querySelector<HTMLSelectElement>('select[aria-label="成员范围"]')!
    scope.value = 'all'; scope.dispatchEvent(new Event('change', { bubbles: true }))
    await flushPromises()
    expect(apiMocks.getMembers).toHaveBeenLastCalledWith(expect.objectContaining({ org_unit_id: '' }), expect.any(AbortSignal))
    wrapper.unmount()
  })

  it('opens an accessible avatar preview, closes with Escape, and restores focus', async () => {
    const trigger = document.createElement('button')
    document.body.appendChild(trigger)
    trigger.focus()
    const wrapper = mount(AvatarPreviewDialog, {
      props: { member: onlineMember },
      attachTo: document.body,
    })
    await nextTick()
    await nextTick()

    const dialog = document.body.querySelector<HTMLElement>('[role="dialog"]')!
    expect(dialog.getAttribute('aria-modal')).toBe('true')
    expect(dialog.textContent).toContain('工程师 · 华康A · 工程部')
    expect(document.activeElement?.getAttribute('aria-label')).toBe('关闭头像预览')
    dialog.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await nextTick()
    expect(wrapper.emitted('close')).toHaveLength(1)
    await wrapper.setProps({ member: null })
    await nextTick()
    expect(document.activeElement).toBe(trigger)
    wrapper.unmount()
  })

  it('renders internal factory and department codes as Chinese labels', () => {
    const wrapper = mount(MemberRow, { props: { member: onlineMember } })

    expect(wrapper.text()).toContain('华康A · 工程部')
    expect(wrapper.text()).not.toContain('huakang-a')
    expect(wrapper.text()).not.toContain('engineering')
  })
})
