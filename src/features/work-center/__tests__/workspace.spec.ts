import { DOMWrapper, flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter, type LocationQueryRaw } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AuthMeResponse } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
import { useWorkCenterStore } from '@/stores/workCenter'
import Workspace from '@/views/NotificationCenterView.vue'
import WorkSnoozePopover from '../WorkSnoozePopover.vue'
import { entry, snap } from './fixtures'

const api = vi.hoisted(() => ({ snapshot: vi.fn(), entry: vi.fn(), patch: vi.fn(), batch: vi.fn(), events: vi.fn(), preferences: vi.fn() }))
vi.mock('@/api/workCenter', () => ({ workCenterApi: api }))

function deferred<T>() {
  let resolve!: (value: T) => void, reject!: (reason: Error) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

let wrapper: VueWrapper
let pinia: ReturnType<typeof createPinia>
let center: ReturnType<typeof useWorkCenterStore>
beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  useAuthStore().$patch({ currentUser: { id: 'test-viewer' } as AuthMeResponse })
  center = useWorkCenterStore()
  vi.resetAllMocks()
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener() {}, removeEventListener() {} }))
  api.snapshot.mockImplementation(async () => snap([entry('A'), entry('B'), entry('C')]))
  api.entry.mockImplementation(async (id: string) => entry(id))
  api.events.mockResolvedValue({ items: [], next_cursor: null })
  api.preferences.mockResolvedValue({ sound_enabled: false, toast_level: 'assigned', version: 0 })
  api.patch.mockImplementation(async (id: string) => entry(id))
})
afterEach(() => {
  wrapper?.unmount()
  document.body.replaceChildren()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
async function workspace(query: LocationQueryRaw = {}) {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/notifications', name: 'notification-center', component: Workspace },
  ] })
  await router.push({ name: 'notification-center', query })
  wrapper = mount(Workspace, { attachTo: document.body, global: { plugins: [pinia, router] } })
  await flushPromises()
  return router
}
function button(label: string, scope: VueWrapper | DOMWrapper<Element> = wrapper) {
  const match = scope.findAll('button').find(node => node.text().trim() === label)
  if (!match) throw new Error('Missing button ' + label)
  return match
}

describe('work center route and selection', () => {
  it('switches the detail layout on the CSS media boundary without a window resize', async () => {
    const desktopBoundary = Object.assign(new EventTarget(), { matches: false })
    vi.stubGlobal('matchMedia', (query: string) => query === '(width < 1024px)'
      ? desktopBoundary : Object.assign(new EventTarget(), { matches: false }))
    await workspace()
    expect(wrapper.find('.nc-focus').exists()).toBe(true)
    desktopBoundary.dispatchEvent(Object.assign(new Event('change'), { matches: true }))
    await flushPromises()
    expect(wrapper.find('.nc-focus').exists()).toBe(false)
    desktopBoundary.dispatchEvent(Object.assign(new Event('change'), { matches: false }))
    await flushPromises()
    expect(wrapper.find('.nc-focus').exists()).toBe(true)
  })
  it.each(['manual', 'background'])('opens only the current deep link after %s recovery', async (mode) => {
    api.snapshot.mockRejectedValueOnce(new Error('暂时无法同步'))
    const router = await workspace({ entry: 'A', module: 'molding' })
    expect(api.entry).not.toHaveBeenCalled()
    await router.replace({ query: { ...router.currentRoute.value.query, entry: 'B' } })
    if (mode === 'manual') await button('重新同步').trigger('click')
    else await center.refresh(true)
    await flushPromises()
    expect(api.entry.mock.calls).toEqual([['B']])
    expect(center.selected?.id).toBe('B')
    await center.refresh()
    await flushPromises()
    expect(api.entry).toHaveBeenCalledOnce()
  })
  it('clears detail loading on failure even if an unrelated URL parameter changes', async () => {
    const read = deferred<ReturnType<typeof entry>>()
    api.entry.mockReturnValueOnce(read.promise)
    const router = await workspace({ entry: 'A' })
    expect(wrapper.get('.nc-focus').text()).toContain('正在读取事项')
    await router.replace({ query: { entry: 'A', from: 'bell' } })
    read.reject(new Error('详情暂时不可用'))
    await flushPromises()
    expect(wrapper.get('.nc-focus').text()).toContain('详情暂时不可用')
    expect(api.entry).toHaveBeenCalledOnce()
    await wrapper.get('[data-work-entry="A"]').trigger('click')
    await flushPromises()
    expect(center.selected?.id).toBe('A')
  })
  it('keeps the newer detail loading when an earlier request completes', async () => {
    const first = deferred<ReturnType<typeof entry>>(), second = deferred<ReturnType<typeof entry>>()
    api.entry.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const router = await workspace({ entry: 'A' })
    await router.replace({ query: { entry: 'B' } })
    first.resolve(entry('A'))
    await flushPromises()
    expect(wrapper.get('.nc-focus').text()).toContain('正在读取事项')
    second.resolve(entry('B'))
    await flushPromises()
    expect(center.selected?.id).toBe('B')
  })
  it('restores the URL filters and detail only when permission returns', async () => {
    await workspace({ module: 'molding', entry: 'A' })
    center.accessDenied({ response: { status: 403 } })
    await flushPromises()
    expect(center.selected).toBeNull()
    await center.refresh(true)
    await flushPromises()
    expect(center.query.module).toBe('molding')
    expect(center.selected?.id).toBe('A')
    expect(api.entry.mock.calls).toEqual([['A'], ['A']])
  })
  it('scopes shortcuts to workspace focus and serializes repeated pin keys', async () => {
    await workspace({ entry: 'A' })
    const outside = document.body.appendChild(document.createElement('a'))
    outside.href = '#shell'
    outside.focus()
    expect(outside.dispatchEvent(new KeyboardEvent('keydown', { key: '/', bubbles: true, cancelable: true }))).toBe(true)
    expect(document.activeElement).toBe(outside)
    const row = wrapper.get('[data-work-entry="A"]')
    await row.trigger('keydown', { key: '/' })
    const search = wrapper.get('[data-work-search]')
    expect(document.activeElement).toBe(search.element)
    const write = deferred<ReturnType<typeof entry>>()
    api.patch.mockClear().mockReturnValueOnce(write.promise)
    await search.trigger('keydown', { key: 'p' })
    expect(api.patch).not.toHaveBeenCalled()
    await row.trigger('keydown', { key: 'p' })
    await row.trigger('keydown', { key: 'p', repeat: true })
    expect(api.patch.mock.calls).toEqual([['A', { pinned: true, state_version: 0 }]])
    write.resolve(entry('A'))
    await flushPromises()
  })
  it.each(['unchanged', 'cancel', 'reselect', 'filter'])('preserves the %s selection after a partial batch failure', async (change) => {
    const router = await workspace()
    const check = (id: string) => wrapper.get('[aria-label="勾选 ' + id + '"]').trigger('click')
    await check('A')
    await check('B')
    const write = deferred<{ results: { id: string; status: string; message?: string }[] }>()
    api.batch.mockReturnValueOnce(write.promise)
    await button('标为已读').trigger('click')
    if (change === 'cancel' || change === 'reselect') await button('取消').trigger('click')
    if (change === 'filter') await router.replace({ query: { module: 'molding' } })
    if (change === 'reselect' || change === 'filter') await check('C')
    write.resolve({ results: [{ id: 'A', status: 'error', message: '版本已变化' }, { id: 'B', status: 'ok' }] })
    await flushPromises()
    const selected = wrapper.findAll('.nc-row [role="checkbox"][aria-checked="true"]').map(el => el.attributes('aria-label'))
    expect(selected).toEqual(change === 'unchanged' ? ['勾选 A'] : change === 'cancel' ? [] : ['勾选 C'])
    expect(center.feedback).toContain('版本已变化')
  })
})

describe('snooze at submission', () => {
  it('schedules batch reminders from the time of the click', async () => {
    let elapsed = 0
    vi.spyOn(performance, 'now').mockImplementation(() => elapsed)
    await workspace()
    elapsed += 15 * 60_000
    api.batch.mockResolvedValue({ results: [] })
    await wrapper.get('[aria-label="勾选 A"]').trigger('click')
    await button('稍后 1 小时').trigger('click')
    expect(api.batch).toHaveBeenCalledWith([{ id: 'A', state_version: 0, snoozed_until: '2026-09-28T03:15:00.000Z' }])
    await flushPromises()
  })
  it('uses elapsed server time for one hour and rejects a custom time that expired while open', async () => {
    let elapsed = 0
    vi.spyOn(performance, 'now').mockImplementation(() => elapsed)
    await center.refresh()
    elapsed += 10 * 60_000
    const data = center.snapshot!
    wrapper = mount(WorkSnoozePopover, { attachTo: document.body, props: { entry: entry(), serverTime: data.context.server_time },
      global: { plugins: [pinia] } })
    await wrapper.get('[data-snooze-entry]').trigger('click')
    const page = new DOMWrapper(document.body)
    const menu = await vi.waitFor(() => page.get('.nc-snooze'))
    await vi.waitFor(() => expect(menu.element.parentElement?.style.transform).toMatch(/^translate\([^%]+px, [^%]+px\)$/))
    await button('自定义上海时间', menu).trigger('click')
    await menu.get('input[type="datetime-local"]').setValue('2026-09-28T10:11')
    expect(button('确定', menu).attributes('disabled')).toBeUndefined()
    elapsed += 2 * 60_000
    await button('确定', menu).trigger('click')
    expect(api.patch).not.toHaveBeenCalled()
    expect(button('确定', menu).attributes('disabled')).toBeDefined()
    const hour = menu.findAll('button').find(el => el.text().includes('1 小时后'))!
    await hour.trigger('click')
    await flushPromises()
    expect(api.patch).toHaveBeenCalledWith('first', { state_version: 0, snoozed_until: '2026-09-28T03:12:00.000Z' })
  })
})
