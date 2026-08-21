import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import AvatarPreviewDialog from '@/components/directory/AvatarPreviewDialog.vue'
import MemberDirectoryDrawer from '@/components/directory/MemberDirectoryDrawer.vue'
import MemberDirectoryEntry from '@/components/directory/MemberDirectoryEntry.vue'
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
        plugins: [createPinia()],
        stubs: { RouterLink: { template: '<a><slot /></a>' } },
      },
    })
    await flushPromises()

    expect(wrapper.get('button').text()).toContain('成员目录')
    expect(wrapper.get('button').text()).toContain('1/2 在线')
    expect(wrapper.get('button').attributes('aria-label')).toBe('打开组织成员目录，1 人在线，共 2 人')
    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(document.body.textContent).toContain('组织成员')
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
    expect(apiMocks.getMembers).toHaveBeenLastCalledWith(expect.objectContaining({ q: '测试' }))

    const findButton = (label: string) => Array.from(document.body.querySelectorAll('button'))
      .find((button) => button.textContent?.trim() === label)!
    findButton('在线').click()
    await flushPromises()
    expect(apiMocks.getMembers).toHaveBeenLastCalledWith(expect.objectContaining({ presence: 'online' }))
    expect(document.body.querySelector<HTMLElement>('[data-testid="presence-pill-indicator"]')?.style.transform)
      .toBe('translateX(100%)')

    findButton('当前厂区').click()
    await flushPromises()
    expect(apiMocks.getMembers).toHaveBeenLastCalledWith(expect.objectContaining({ factory_id: 'huakang-a' }))
    expect(document.body.textContent).toContain('已限定当前厂区')

    findButton('当前部门').click()
    await flushPromises()
    expect(apiMocks.getMembers).toHaveBeenLastCalledWith(expect.objectContaining({ department: 'engineering' }))
    expect(document.body.textContent).toContain('已限定当前厂区与当前部门')
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
})
