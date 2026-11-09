import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import View from './ProcessDatesView.vue'
import { trialApi as api, type DateDemand } from './api'

vi.mock('@/stores/auth', async () => {
  const { reactive } = await import('vue')
  const store = reactive({ sessionVersion: 1, authorizationVersion: 1 })
  return { useAuthStore: () => store }
})
const demand = (): DateDemand => ({ id: 'd1', version: 2, status: 'AWAITING_PROCESS_DATES', item_no: '001', owner_name: '业务甲合成记录',
  quantity: '100', unit: '套', lines: [], processes: ['裁床', '车缝'], process_dates: {}, occurred_at: '2026-11-04' })
let wrapper: VueWrapper
const button = (name: string) => wrapper.findAll('button').find(b => b.text() === name)!
async function start(row = demand(), write = true, factory = 'huakang-c') {
  vi.spyOn(api, 'dateAccess').mockResolvedValue({ enabled: true, schema_ready: true, can_write: write })
  vi.spyOn(api, 'dateWorkspace').mockResolvedValue({ items: [row] })
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: View }] })
  await router.push(`/modules/pmc-warehouse/process-material-dates?factory=${factory}`); await router.isReady()
  wrapper = mount({ template: '<RouterView />' }, { global: { plugins: [router] } }); await flushPromises()
  return router
}
beforeEach(() => { vi.restoreAllMocks(); vi.spyOn(window, 'confirm').mockReturnValue(true) })
afterEach(() => wrapper?.unmount())

describe('procurement process dates', () => {
  it('saves all process keys, leaving blank dates explicitly null', async () => {
    await start(); await button('查看／填期').trigger('click')
    const save = vi.spyOn(api, 'saveDates').mockResolvedValue({ ...demand(), version: 3, process_dates: { 裁床: '2026-11-12' } })
    await wrapper.get('input[aria-label="裁床物料期"]').setValue('2026-11-12')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(save.mock.calls[0]![1]).toMatchObject({ expected_version: 2, dates: { 裁床: '2026-11-12', 车缝: null } })
    expect(wrapper.text()).toContain('物料期已保存')
  })
  it('retries the identical request after uncertain writes and locks competing actions', async () => {
    await start(); await button('查看／填期').trigger('click')
    const save = vi.spyOn(api, 'saveDates').mockRejectedValueOnce(new Error('连接中断')).mockResolvedValueOnce(demand())
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined()
    expect(button('刷新需求').attributes('disabled')).toBeDefined()
    await button('核对并重试原请求').trigger('click'); await flushPromises()
    expect(save.mock.calls[1]).toEqual(save.mock.calls[0])
  })
  it('uses current reviewed state after replaying an older successful date receipt', async () => {
    await start(); await button('查看／填期').trigger('click')
    vi.spyOn(api, 'saveDates').mockResolvedValue({ ...demand(), version: 3, status: 'AWAITING_SELF_REVIEW' })
    vi.mocked(api.dateWorkspace).mockResolvedValue({ items: [{ ...demand(), version: 4, status: 'SELF_REVIEWED_DATA_PENDING' }] })
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('业务已自审；修改前须由业务退回')
  })
  it.each([false, true])('keeps read-only or reviewed requests locked (reviewed=%s)', async reviewed => {
    const row = demand(); if (reviewed) row.status = 'SELF_REVIEWED_DATA_PENDING'
    await start(row, reviewed); await button('查看／填期').trigger('click')
    expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined()
  })
  it('clears evidence when permissions are revoked and ignores late writes', async () => {
    await start(); await button('查看／填期').trigger('click')
    let finish!: (row: DateDemand) => void
    vi.spyOn(api, 'saveDates').mockImplementation(() => new Promise(resolve => { finish = resolve }))
    await wrapper.get('form').trigger('submit')
    vi.mocked(api.dateAccess).mockRejectedValue({ response: { status: 403, data: { detail: '无权限' } } })
    useAuthStore().authorizationVersion++; await flushPromises()
    finish(demand()); await flushPromises()
    expect(wrapper.text()).toContain('无权限')
    expect(wrapper.text()).not.toContain('业务甲合成记录')
    expect(wrapper.find('form').exists()).toBe(false)
  })
  it('does not load another factory and warns before discarding dates', async () => {
    await start(demand(), true, 'huakang-a')
    expect(api.dateAccess).not.toHaveBeenCalled()
    wrapper.unmount()
    const router = await start(); await button('查看／填期').trigger('click')
    await wrapper.get('input[aria-label="裁床物料期"]').setValue('2026-11-12')
    vi.mocked(window.confirm).mockReturnValue(false)
    await router.push('/elsewhere?factory=huakang-c')
    expect(router.currentRoute.value.path).toContain('process-material-dates')
  })
})
