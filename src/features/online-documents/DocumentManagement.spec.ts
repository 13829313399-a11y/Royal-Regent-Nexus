import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { AxiosError } from 'axios'
import Management from './DocumentManagement.vue'
import { onlineDocuments as api, type OnlineDocument } from '@/api/onlineDocuments'
import * as sdk from './editor'

const document = (): OnlineDocument => ({ id: 'd1', title: '十月进出货', format: 'xlsx', owner_name: '测试用户', access: 'owner', revision: 2, editing: false, byte_size: 100, grants: [], state_version: 3, deleted_at: '', protected: false, updated_at: '', created_at: '', pending_save: '', saved_request: '', save_error: '' })
let wrapper: VueWrapper | undefined
const button = (label: string) => wrapper!.findAll('button').find(b => b.text() === label)!
async function render(doc = document()) { wrapper = mount(Management, { attachTo: globalThis.document.body, props: { factoryId: 'group', document: doc }, global: { stubs: { DialogPortal: { template: '<div><slot /></div>' } } } }); await flushPromises() }
beforeEach(() => {
  vi.spyOn(api, 'history').mockResolvedValue({ items: [2, 1].map(r => ({ revision: r, current: r === 2, byte_size: 100, actor_id: 'owner', created_at: '2026-10-26T00:00:00Z' })), next_before: null })
  vi.spyOn(api, 'events').mockResolvedValue({ items: [], next_before: null })
  vi.spyOn(api, 'protection').mockResolvedValue({ document: document(), sheets: [{ name: '进出货', formula_count: 3, used_cells: 20 }], rules: [] })
  vi.spyOn(api, 'command').mockResolvedValue({ ...document(), revision: 3, state_version: 4 })
  vi.spyOn(api, 'downloadRevision').mockResolvedValue(new Blob(['file']))
  vi.spyOn(sdk, 'downloadBlob').mockImplementation(() => {})
})
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.restoreAllMocks() })

describe('文档管理恢复边界', () => {
  it('names the selected file in the modal and retains it across detail sections', async () => {
    await render()
    const dialog = wrapper!.get('[role="dialog"]')
    expect(dialog.attributes('aria-modal')).toBe('true')
    expect(wrapper!.get('h2').text()).toBe('十月进出货.xlsx · 历史版本')
    expect(api.history).toHaveBeenCalledWith('group', 'd1', 0)
    await button('操作记录').trigger('click'); await flushPromises()
    expect(wrapper!.get('h2').text()).toBe('十月进出货.xlsx · 操作记录')
    expect(api.events).toHaveBeenCalledWith('group', 'd1', '')
  })
  it('requires a concrete restore confirmation and keeps the observed base version', async () => {
    await render(); await button('恢复此版本').trigger('click')
    expect(api.command).not.toHaveBeenCalled()
    expect(wrapper!.text()).toContain('现在的内容仍保留')
    await button('确认操作').trigger('click'); await flushPromises()
    expect(api.command).toHaveBeenCalledWith('group', 'd1', 'restore', expect.objectContaining({ expected_version: 3, revision: 1 }))
    expect(wrapper!.emitted('changed')?.[0]?.[1]).toContain('已恢复为版本 3')
  })
  it('retries an unknown result with the exact command and blocks leaving or changing it', async () => {
    vi.mocked(api.command).mockRejectedValueOnce(new AxiosError('network timeout'))
    await render(); await button('恢复此版本').trigger('click'); await button('确认操作').trigger('click'); await flushPromises()
    const original = vi.mocked(api.command).mock.calls[0]![3]
    expect(button('关闭详情').attributes('disabled')).toBeDefined()
    await wrapper!.get('[role="dialog"]').trigger('keydown', { key: 'Escape' })
    expect(wrapper!.emitted('close')).toBeUndefined()
    expect(button('取消').attributes('disabled')).toBeDefined()
    expect(wrapper!.emitted('pending')?.at(-1)).toEqual([true])
    await button('重试原操作').trigger('click'); await flushPromises()
    expect(vi.mocked(api.command).mock.calls[1]![3]).toEqual(original)
    expect(wrapper!.emitted('changed')).toHaveLength(1)
  })
  it('does not report an old retry as a fresh current-state change', async () => {
    vi.mocked(api.command).mockResolvedValue({ ...document(), operation_notice: '原操作已完成，但文档后来又有变化，请以当前列表为准' })
    await render(); await button('恢复此版本').trigger('click'); await button('确认操作').trigger('click'); await flushPromises()
    expect(wrapper!.emitted('changed')?.[0]?.[1]).toContain('后来又有变化')
  })
  it('makes the recycle-bin consequence explicit and hides content/history of deleted files', async () => {
    await render({ ...document(), deleted_at: '2026-10-26T00:00:00Z' })
    expect(api.history).not.toHaveBeenCalled()
    expect(button('历史版本')).toBeUndefined()
    await button('恢复到文档列表').trigger('click')
    expect(wrapper!.text()).toContain('默认仅自己可见')
    await button('确认操作').trigger('click'); await flushPromises()
    expect(api.command).toHaveBeenCalledWith('group', 'd1', 'recover', expect.objectContaining({ expected_version: 3 }))
  })
  it('retains protection input after a definitive validation failure', async () => {
    vi.mocked(api.command).mockRejectedValue(new AxiosError('invalid range', 'ERR_BAD_REQUEST', undefined, undefined, { status: 422, data: { detail: '填写区域超出工作表范围' } } as never))
    await render(); await button('公式区域保护').trigger('click'); await flushPromises()
    await wrapper!.get('input').setValue('b2:d100，F2:F10')
    await button('启用保护').trigger('click'); await button('确认操作').trigger('click'); await flushPromises()
    expect(wrapper!.get('input').element).toHaveProperty('value', 'b2:d100，F2:F10')
    expect(api.command).toHaveBeenCalledWith('group', 'd1', 'protection', expect.objectContaining({ rules: [{ sheet: '进出货', ranges: ['B2:D100', 'F2:F10'] }] }))
    expect(wrapper!.emitted('changed')).toBeUndefined()
  })
  it('blocks restore while protected or still editing', async () => {
    await render({ ...document(), editing: true, protected: true })
    expect(button('恢复此版本').attributes('disabled')).toBeDefined()
    expect(wrapper!.text()).toContain('解除公式区域保护')
  })
  it('ignores an outstanding operation response after unmount at an account boundary', async () => {
    let resolve!: (d: OnlineDocument) => void
    vi.mocked(api.command).mockImplementation(() => new Promise(r => { resolve = r }))
    await render(); await button('恢复此版本').trigger('click'); await button('确认操作').trigger('click')
    const old = wrapper!; old.unmount(); wrapper = undefined
    resolve(document()); await flushPromises()
    expect(old.emitted('changed')).toBeUndefined()
  })
})
