import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import View from './MaterialBomUsage.vue'
import { engineeringApi as api, type Material, type MaterialBomUsage } from './api'

let wrapper: VueWrapper
const material = (): Material => ({ id: 'm1', code: '04-01-00001', name: '裁片', version: 4, status: 'ACTIVE', data: { unit: '套' } })
const report = (): MaterialBomUsage => ({ material_id: 'm1', material_version: 4, code: '04-01-00001', name: '裁片', checked_at: 'CHECK_TIME', bom_count: 1,
  items: ['自制', '委外'].map((attribute, index) => ({ bom_id: 'b1', bom_version: 3, item_no: '001', bom_name: '测试成品', status: 'DRAFT', roles: ['LATEST'],
    row: index + 1, key: `k${index}`, material_version: index + 2, code: '04-01-00001', name: '裁片', attribute, process: '裁床', unit: '码', numerator: '0.0297', denominator: '2' })) })
const start = (disabled = false) => { wrapper = mount(View, { props: { material: material(), disabled } }) }
beforeEach(() => vi.restoreAllMocks())
afterEach(() => wrapper?.unmount())

describe('material BOM references', () => {
  it('loads the selected saved material and keeps occurrences and attributes separate', async () => {
    vi.spyOn(api, 'materialUsage').mockResolvedValue(report()); start(); await flushPromises()
    expect(api.materialUsage).toHaveBeenCalledWith('m1', 4)
    expect(wrapper.findAll('tbody tr')).toHaveLength(2)
    expect(wrapper.text()).toContain('自制'); expect(wrapper.text()).toContain('委外')
    expect(wrapper.text()).toContain('最新保存版'); expect(wrapper.text()).toContain('0.0297 ／ 2')
    expect(wrapper.text()).toContain('不累加为需求量'); expect(wrapper.text()).toContain('正式下发仍未开放')
  })
  it('shows combined roles once and explains the limited empty result scope', async () => {
    const r = report(); r.items = [{ ...r.items[0]!, roles: ['LATEST', 'EFFECTIVE'], status: 'APPROVED' }]
    vi.spyOn(api, 'materialUsage').mockResolvedValueOnce(r).mockResolvedValueOnce({ ...r, bom_count: 0, items: [] })
    start(); await flushPromises()
    expect(wrapper.findAll('tbody tr')).toHaveLength(1)
    expect(wrapper.text()).toContain('最新保存版／当前有效版')
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('不代表历史单据或其他模块没有使用')
  })
  it('discards in-flight results on edits and fetches the updated material after re-enabling', async () => {
    let finish!: (value: MaterialBomUsage) => void
    vi.spyOn(api, 'materialUsage').mockImplementationOnce(() => new Promise(resolve => { finish = resolve })).mockResolvedValue(report())
    start(); await wrapper.setProps({ disabled: true }); finish(report()); await flushPromises()
    expect(wrapper.text()).not.toContain('CHECK_TIME'); expect(wrapper.get('button').attributes('disabled')).toBeDefined()
    await wrapper.setProps({ material: { ...material(), version: 5 }, disabled: false }); await flushPromises()
    expect(api.materialUsage).toHaveBeenLastCalledWith('m1', 5)
  })
  it('switches material identity without restoring an older response', async () => {
    let finish!: (value: MaterialBomUsage) => void
    vi.spyOn(api, 'materialUsage').mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
      .mockResolvedValueOnce({ ...report(), material_id: 'm2', items: [], bom_count: 0 })
    start(); await wrapper.setProps({ material: { ...material(), id: 'm2' } }); await flushPromises()
    finish(report()); await flushPromises()
    expect(api.materialUsage).toHaveBeenLastCalledWith('m2', 4)
    expect(wrapper.findAll('tbody tr')).toHaveLength(0)
  })
  it('does not treat conflicts as no references and delegates denied access', async () => {
    const denied = { response: { status: 403, data: { detail: '无权限' } } }
    vi.spyOn(api, 'materialUsage').mockRejectedValueOnce({ response: { status: 409, data: { detail: '物料已变化，请刷新资料后重新打开 BOM 引用' } } }).mockRejectedValueOnce(denied)
    start(); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('物料已变化')
    expect(wrapper.text()).not.toContain('未查到此物料引用')
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(wrapper.emitted('denied')).toEqual([[denied]])
  })
})
