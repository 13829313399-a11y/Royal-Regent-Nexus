import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import View from './BomVersionComparison.vue'
import { engineeringApi as api, emptyBom, type Bom, type BomComparison } from './api'

let wrapper: VueWrapper
const versions = (): Bom[] => [2, 1].map(version => ({ id: 'b1', version, status: version === 1 ? 'APPROVED' : 'DRAFT', effective_version: 1, data: emptyBom(), materials: {} }))
const report = (): BomComparison => ({ id: 'b1', from_version: 1, to_version: 2, from_status: 'APPROVED', to_status: 'DRAFT', unchanged_count: 1,
  header: [{ field: 'name', label: 'BOM 名称', before: '旧成品', after: '新成品' }], rows: [{ key: 'leaf', kind: 'CHANGED',
    before: { code: '04-001', name: '裁片', material_version: 1, attribute: '自制', path: '成品 → 裁片', cumulative: '297/10000', unit: '码', numerator: '0.0297', denominator: '2' },
    after: { code: '04-001', name: '裁片', material_version: 2, attribute: '委外', path: '成品 → 手工 → 裁片', cumulative: '297/5000', unit: '码', numerator: '0.0297', denominator: '2' },
    changes: [{ field: 'path', label: '层级路径' }, { field: 'attribute', label: '物料属性' }, { field: 'cumulative', label: '沿路径单套用量' }] }] })
const start = (disabled = false) => { wrapper = mount(View, { props: { versions: versions(), disabled } }) }
beforeEach(() => vi.restoreAllMocks())
afterEach(() => wrapper?.unmount())

describe('engineering BOM version comparison', () => {
  it('compares saved versions and displays statuses, paths, attributes and exact usage', async () => {
    start(); const request = vi.spyOn(api, 'compare').mockResolvedValue(report())
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(request).toHaveBeenCalledWith('b1', 1, 2)
    expect(wrapper.text()).toContain('v1（已审核）→ v2（待审核）')
    expect(wrapper.text()).toContain('自制'); expect(wrapper.text()).toContain('委外')
    expect(wrapper.text()).toContain('297/10000'); expect(wrapper.text()).toContain('297/5000')
    expect(wrapper.text()).toContain('成品 → 手工 → 裁片')
    expect(wrapper.text()).toContain('正式下发仍未开放')
  })
  it('invalidates an in-flight comparison when version selection or editing state changes', async () => {
    start(); let finish!: (value: BomComparison) => void
    vi.spyOn(api, 'compare').mockImplementation(() => new Promise(resolve => { finish = resolve }))
    await wrapper.get('button').trigger('click')
    await wrapper.get('select[aria-label="比较原版本"]').setValue(2)
    finish(report()); await flushPromises()
    expect(wrapper.text()).not.toContain('新成品'); expect(wrapper.get('button').attributes('disabled')).toBeDefined()
    await wrapper.get('select[aria-label="比较原版本"]').setValue(1)
    vi.mocked(api.compare).mockResolvedValue(report())
    await wrapper.get('button').trigger('click'); await flushPromises(); expect(wrapper.text()).toContain('新成品')
    await wrapper.setProps({ disabled: true })
    expect(wrapper.text()).not.toContain('新成品'); expect(wrapper.get('button').attributes('disabled')).toBeDefined()
  })
  it('clears comparison when switching the history document', async () => {
    start(); vi.spyOn(api, 'compare').mockResolvedValue(report())
    await wrapper.get('button').trigger('click'); await flushPromises()
    await wrapper.setProps({ versions: versions().map(v => ({ ...v, id: 'b2' })) })
    expect(wrapper.text()).not.toContain('新成品')
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(api.compare).toHaveBeenLastCalledWith('b2', 1, 2)
  })
  it('clears results and signals the parent on revoked access', async () => {
    start(); const denied = { response: { status: 403, data: { detail: '无权限' } } }
    vi.spyOn(api, 'compare').mockRejectedValue(denied)
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(wrapper.emitted('denied')).toEqual([[denied]])
    expect(wrapper.text()).not.toContain('新成品')
  })
})
