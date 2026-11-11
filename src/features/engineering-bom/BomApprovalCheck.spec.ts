import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import View from './BomApprovalCheck.vue'
import { engineeringApi as api, emptyBom, type Bom, type BomApprovalCheck } from './api'

let wrapper: VueWrapper
const bom = (): Bom => ({ id: 'b1', version: 3, status: 'DRAFT', effective_version: 2, data: emptyBom(), materials: {} })
const report = (): BomApprovalCheck => ({ id: 'b1', version: 3, status: 'DRAFT', effective_version: 2,
  checked_at: '2026-11-05T12:00:00+08:00', checked_rows: 3, ready_for_approval: false, can_release: false,
  issues: ['自制', '委外'].map((attribute, index) => ({ row: index + 2, key: `k${index}`, code: '04-01-00001', name: '裁片', attribute, message: '请确认每一行所属工序' })) })
const start = () => { wrapper = mount(View, { props: { bom: bom() } }) }
beforeEach(() => vi.restoreAllMocks())
afterEach(() => wrapper?.unmount())

describe('BOM approval preparation', () => {
  it('checks the saved version and displays same-code occurrences with their own attributes', async () => {
    start(); vi.spyOn(api, 'approvalCheck').mockResolvedValue(report())
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(api.approvalCheck).toHaveBeenCalledWith('b1', 3)
    expect(wrapper.findAll('li')).toHaveLength(2)
    expect(wrapper.text()).toContain('自制'); expect(wrapper.text()).toContain('委外')
    expect(wrapper.text()).toContain('第 2 行'); expect(wrapper.text()).toContain('第 3 行')
    expect(wrapper.text()).toContain('正式下发仍未开放')
  })
  it('does not present a successful check as approval or release', async () => {
    start(); vi.spyOn(api, 'approvalCheck').mockResolvedValue({ ...report(), ready_for_approval: true, issues: [] })
    const write = vi.spyOn(api, 'post')
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('仍需执行工程审核')
    expect(write).not.toHaveBeenCalled()
  })
  it('clears completed reports and discards in-flight results when editing or versions change', async () => {
    start(); vi.spyOn(api, 'approvalCheck').mockResolvedValue(report())
    await wrapper.get('button').trigger('click'); await flushPromises()
    await wrapper.setProps({ disabled: true }); expect(wrapper.findAll('li')).toHaveLength(0)
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
    await wrapper.setProps({ disabled: false })
    let finish!: (value: BomApprovalCheck) => void
    vi.mocked(api.approvalCheck).mockImplementation(() => new Promise(resolve => { finish = resolve }))
    await wrapper.get('button').trigger('click'); await wrapper.setProps({ bom: { ...bom(), version: 4 } })
    finish(report()); await flushPromises(); expect(wrapper.findAll('li')).toHaveLength(0)
    vi.mocked(api.approvalCheck).mockResolvedValue({ ...report(), version: 4 })
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(api.approvalCheck).toHaveBeenLastCalledWith('b1', 4)
  })
  it('invalidates a pending response on document switch', async () => {
    start(); let finish!: (value: BomApprovalCheck) => void
    vi.spyOn(api, 'approvalCheck').mockImplementation(() => new Promise(resolve => { finish = resolve }))
    await wrapper.get('button').trigger('click'); await wrapper.setProps({ bom: { ...bom(), id: 'b2' } })
    finish(report()); await flushPromises(); expect(wrapper.text()).not.toContain('裁片')
  })
  it('shows version conflicts as errors and delegates authorization failures to the parent', async () => {
    start(); const denied = { response: { status: 403, data: { detail: '权限已撤销' } } }
    vi.spyOn(api, 'approvalCheck').mockRejectedValueOnce({ response: { status: 409, data: { detail: 'BOM 已变化，请刷新' } } }).mockRejectedValueOnce(denied)
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('BOM 已变化')
    expect(wrapper.text()).not.toContain('未发现审核阻断')
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(wrapper.emitted('denied')).toEqual([[denied]])
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })
})
