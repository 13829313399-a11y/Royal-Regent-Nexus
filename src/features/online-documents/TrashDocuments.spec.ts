import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { AxiosError, AxiosHeaders } from 'axios'
import TrashDocuments from './TrashDocuments.vue'
import { onlineDocuments as api, type OnlineDocument } from '@/api/onlineDocuments'

const doc = (id: string): OnlineDocument => ({ id, title: `月报-${id}`, format: 'xlsx', owner_name: '拥有者', access: 'owner', revision: 1, state_version: 7, editing: false, byte_size: 10, deleted_at: '', protected: false, updated_at: '', created_at: '', pending_save: '', saved_request: '', save_error: '' })
let wrapper: VueWrapper | undefined
const button = (label: string) => wrapper!.findAll('button').find(b => b.text() === label)!
const rejected = (status: number) => new AxiosError('请求失败', undefined, undefined, undefined, { status, data: { detail: '文档状态已变化' }, statusText: '', headers: new AxiosHeaders(), config: { headers: new AxiosHeaders() } })
async function render() { wrapper = mount(TrashDocuments, { props: { factoryId: 'group', documents: [doc('a'), doc('b')] } }); await flushPromises() }

beforeEach(() => {
  vi.spyOn(api, 'detail').mockImplementation(async (_factory, id) => doc(id))
  vi.spyOn(api, 'command').mockImplementation(async (_factory, id) => ({ ...doc(id), deleted_at: '2026-10-28', state_version: 8 }))
})
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.restoreAllMocks() })

describe('列表批量移入回收站', () => {
  it('previews the actual filenames and requires confirmation before any mutation', async () => {
    await render()
    expect(wrapper!.get('[aria-label="待移入回收站的文档"]').text()).toContain('月报-a.xlsx')
    expect(api.command).not.toHaveBeenCalled()
    await button('取消').trigger('click')
    expect(wrapper!.emitted('close')).toHaveLength(1)
    expect(api.command).not.toHaveBeenCalled()
  })

  it('uses fresh versions and distinct receipts for each file and reports completion', async () => {
    await render(); await button('确认移入 2 份文档').trigger('click'); await flushPromises()
    expect(api.command).toHaveBeenNthCalledWith(1, 'group', 'a', 'trash', { request_id: expect.any(String), expected_version: 7 })
    expect(api.command).toHaveBeenNthCalledWith(2, 'group', 'b', 'trash', { request_id: expect.any(String), expected_version: 7 })
    expect(vi.mocked(api.command).mock.calls[0]![3].request_id).not.toBe(vi.mocked(api.command).mock.calls[1]![3].request_id)
    expect(wrapper!.emitted('changed')).toHaveLength(2)
    expect(wrapper!.emitted('complete')).toEqual([[2]])
  })

  it.each([{ editing: true }, { pending_save: 'pending' }, { save_error: '保存失败' }, { access: 'edit' as const }, { deleted_at: 'already-deleted' }])('blocks the entire selection before mutations when a file is unavailable: %o', async state => {
    vi.mocked(api.detail).mockImplementation(async (_factory, id) => ({ ...doc(id), ...(id === 'b' ? state : {}) }))
    await render()
    expect(wrapper!.get('[role="alert"]').text()).toContain('月报-b.xlsx')
    expect(button('确认移入 2 份文档')).toBeUndefined()
    expect(api.command).not.toHaveBeenCalled()
  })

  it.each([new Error('网络中断'), rejected(408), rejected(503)])('retries only the uncertain file with the original receipt', async failure => {
    vi.mocked(api.command).mockResolvedValueOnce({ ...doc('a'), deleted_at: 'deleted' }).mockRejectedValueOnce(failure)
    await render(); await button('确认移入 2 份文档').trigger('click'); await flushPromises()
    const original = vi.mocked(api.command).mock.calls[1]![3]
    expect(wrapper!.text()).toContain('已确认处理 1 / 2 份')
    expect(button('关闭').attributes('disabled')).toBeDefined()
    expect(wrapper!.emitted('complete')).toBeUndefined()
    await button('重试原操作').trigger('click'); await flushPromises()
    expect(api.command).toHaveBeenCalledTimes(3)
    expect(api.command).toHaveBeenLastCalledWith('group', 'b', 'trash', original)
    expect(wrapper!.emitted('complete')).toEqual([[2]])
  })

  it('stops on a definitive rejection and leaves remaining files untouched', async () => {
    wrapper = mount(TrashDocuments, { props: { factoryId: 'group', documents: [doc('a'), doc('b'), doc('c')] } })
    await flushPromises()
    vi.mocked(api.command).mockResolvedValueOnce({ ...doc('a'), deleted_at: 'deleted' }).mockRejectedValueOnce(rejected(409))
    await button('确认移入 3 份文档').trigger('click'); await flushPromises()
    expect(api.command).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('后续文件尚未处理')
    expect(button('重试原操作')).toBeUndefined()
    expect(button('关闭').attributes('disabled')).toBeUndefined()
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(wrapper.emitted('complete')).toBeUndefined()
  })

  it('stops when an acknowledged retry reports a later recovery or other change', async () => {
    vi.mocked(api.command).mockResolvedValueOnce({ ...doc('a'), operation_notice: '原操作已完成，但文档后来又有变化' })
    await render(); await button('确认移入 2 份文档').trigger('click'); await flushPromises()
    expect(api.command).toHaveBeenCalledOnce()
    expect(wrapper!.text()).toContain('批量操作已停止')
    expect(wrapper!.emitted('complete')).toBeUndefined()
  })

  it('never continues a batch after the parent closes on an identity boundary', async () => {
    let resolve!: (value: OnlineDocument) => void
    vi.mocked(api.command).mockImplementationOnce(() => new Promise(r => { resolve = r }))
    await render(); await button('确认移入 2 份文档').trigger('click'); await flushPromises()
    wrapper!.unmount(); wrapper = undefined
    resolve({ ...doc('a'), deleted_at: 'deleted' }); await flushPromises()
    expect(api.command).toHaveBeenCalledOnce()
  })
})
