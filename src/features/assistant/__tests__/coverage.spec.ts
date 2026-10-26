import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { assistantApi } from '../api'
import AssistantCoverage from '../AssistantCoverage.vue'
import type { ModuleCoverage, ModuleCoverageState } from '../types'

let wrappers: ReturnType<typeof mount>[] = []
beforeEach(() => { setActivePinia(createPinia()); vi.restoreAllMocks() })
afterEach(() => { wrappers.forEach(w => w.unmount()); wrappers = []; document.body.innerHTML = '' })
function result(factory = 'huaxing', states: ModuleCoverageState[] = ['business_read']): ModuleCoverage {
  return { factory_id: factory, checked_at: '2026-10-25T12:00:00+08:00', catalog_scope: 'registered_modules',
    items: states.map(state => ({module_id: state, label: `${factory}-${state}`, state, reason: '当前范围检查', read_only: true, guide_count: 0, verification: 'implemented_unverified'})) }
}
function panel() {
  const w = mount(AssistantCoverage, {attachTo: document.body, props: {page: {module_id: 'spray-production', route_name: 'spray-demands', factory_id: 'huaxing'}}})
  wrappers.push(w); return w
}
describe('current actor module coverage', () => {
  it('returns keyboard focus to refresh when the successful retry control disappears', async () => {
    let resolve!: (value: ModuleCoverage) => void
    vi.spyOn(assistantApi, 'coverage').mockRejectedValueOnce(new TypeError('Failed to fetch')).mockImplementation(() => new Promise(r => { resolve = r }))
    const w = panel(); await flushPromises()
    const retry = w.findAll('button').find(b => b.text() === '重试检查')!
    ;(retry.element as HTMLButtonElement).focus()
    await retry.trigger('click'); await flushPromises()
    expect(document.activeElement).toBe(w.get('section').element)
    resolve(result()); await flushPromises()
    expect(document.activeElement).toBe(w.get('button').element)
    expect(w.findAll('li')).toHaveLength(1)
  })
  it('separates five states from acceptance and retries a failed read without retaining old availability', async () => {
    const api = vi.spyOn(assistantApi, 'coverage').mockResolvedValueOnce(result('huaxing', ['business_read', 'guide_only', 'disabled', 'not_connected', 'forbidden']))
      .mockRejectedValueOnce(new Error('网络不可用')).mockResolvedValueOnce(result())
    const w = panel(); await flushPromises()
    for (const text of ['可只读查询', '仅操作说明', '未启用', '未接入', '无权限', '完整验收待完成']) expect(w.text()).toContain(text)
    await w.get('button').trigger('click'); await flushPromises()
    expect(w.text()).toContain('暂时无法连接，请检查网络后重试。'); expect(w.find('ul').exists()).toBe(false)
    await w.findAll('button').find(b => b.text() === '重试检查')!.trigger('click'); await flushPromises()
    expect(w.findAll('li')).toHaveLength(1); expect(api).toHaveBeenCalledTimes(3)
  })
  it('rejects late responses across A to B to A scopes even if abort is ignored', async () => {
    const resolve: ((value: ModuleCoverage) => void)[] = []
    const api = vi.spyOn(assistantApi, 'coverage').mockImplementation(() => new Promise(r => resolve.push(r)))
    const w = panel()
    await w.setProps({page: {module_id: 'spray-production', route_name: 'spray-demands', factory_id: 'huakang-b'}})
    await w.setProps({page: {module_id: 'spray-production', route_name: 'spray-demands', factory_id: 'huaxing'}})
    expect(api.mock.calls[0]![2].aborted).toBe(true)
    resolve[0]!(result('OLD-A')); resolve[1]!(result('OLD-B')); await flushPromises()
    expect(w.find('ul').exists()).toBe(false)
    resolve[2]!(result('CURRENT-A')); await flushPromises()
    expect(w.text()).toContain('CURRENT-A'); expect(w.text()).not.toContain('OLD-')
  })
  it('clears on authorization change immediately and aborts the pending request on disposal', async () => {
    let resolve!: (value: ModuleCoverage) => void
    const api = vi.spyOn(assistantApi, 'coverage').mockResolvedValueOnce(result()).mockImplementation(() => new Promise(r => {resolve = r}))
    const w = panel(); await flushPromises()
    useAuthStore().authorizationVersion++
    await flushPromises()
    expect(w.find('ul').exists()).toBe(false)
    w.unmount(); wrappers = []
    expect(api.mock.calls[1]![2].aborted).toBe(true)
    resolve(result()); await flushPromises()
  })
  it('keeps the result during a same-identity authorization snapshot refresh', async () => {
    const api = vi.spyOn(assistantApi, 'coverage').mockResolvedValue(result())
    const w = panel(); await flushPromises()
    useAuthStore().effectiveAccess = []; useAuthStore().sessionVersion++
    await flushPromises()
    expect(api).toHaveBeenCalledOnce(); expect(w.find('ul').exists()).toBe(true)
  })
})
