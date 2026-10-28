import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import Workspace from './OnlineDocumentsWorkspace.vue'
import { onlineDocuments as api, type OnlineDocument } from '@/api/onlineDocuments'
import { canChangeFactory } from '@/lib/factoryChangeGuard'
import * as sdk from './editor'
import { http } from '@/lib/http'
import { reactive } from 'vue'

vi.mock('vue-router', () => ({ onBeforeRouteLeave: vi.fn(), RouterLink: { template: '<a><slot /></a>' } }))
const authState = reactive({ currentUser: { id: 'owner', display_name: '测试用户', authorization_version: 1 } })
vi.mock('@/stores/auth', () => ({ useAuthStore: () => authState }))
const document = (): OnlineDocument => ({ id: 'd1', title: '公式试验', format: 'xlsx', owner_name: '测试用户', access: 'owner', revision: 1, editing: false, byte_size: 100, grants: [], share_version: 'acl-v1', state_version: 1, deleted_at: '', protected: false, updated_at: '2026-10-26T02:00:00Z', created_at: '', pending_save: '', saved_request: '', save_error: '' })
let wrapper: VueWrapper | undefined
let events: Record<string, (e?: sdk.EditorEvent) => void>
const destroy = vi.fn()
const construct = vi.fn()
const button = (label: string) => wrapper!.findAll('button').find(b => b.text() === label)!
async function render() { wrapper = mount(Workspace, { props: { factoryId: 'huaxing' } }); await flushPromises() }
async function open() { await button('打开').trigger('click'); await flushPromises(); events.onDocumentReady!(); await flushPromises() }

beforeEach(() => {
  localStorage.clear()
  authState.currentUser = { id: 'owner', display_name: '测试用户', authorization_version: 1 }
  vi.useFakeTimers(); destroy.mockReset(); construct.mockReset()
  vi.spyOn(api, 'list').mockResolvedValue([document()])
  vi.spyOn(api, 'folders').mockResolvedValue([{ id: 'folder-1', name: '成品进出', version: 1 }])
  vi.spyOn(api, 'createFolder').mockResolvedValue({ id: 'folder-2', name: '月报', version: 1 })
  vi.spyOn(api, 'move').mockResolvedValue({ moved: 1 })
  vi.spyOn(api, 'copy').mockResolvedValue({ ...document(), id: 'copy', title: '公式试验-副本' })
  vi.spyOn(api, 'renameFolder').mockResolvedValue({ id: 'folder-1', name: '新文件夹', version: 2 })
  vi.spyOn(api, 'editor').mockResolvedValue({ document: document(), config: {}, script_url: 'http://office/api.js' })
  vi.spyOn(api, 'detail').mockResolvedValue(document())
  vi.spyOn(api, 'save').mockResolvedValue({ request_id: 'request1', revision: 1 })
  vi.spyOn(api, 'download').mockResolvedValue(new Blob(['file']))
  vi.spyOn(api, 'recipients').mockResolvedValue([
    { id: 'viewer', display_name: '同事甲', department: '工程部', organization: '华星', epoch: 1 },
    { id: 'editor', display_name: '同事乙', department: '业务部', organization: '华康A', epoch: 1 },
  ])
  vi.spyOn(api, 'share').mockResolvedValue(document())
  vi.spyOn(api, 'rename').mockResolvedValue({ ...document(), title: '十月汇总' })
  vi.spyOn(api, 'history').mockResolvedValue({ items: [], next_before: null })
  vi.spyOn(sdk, 'downloadBlob').mockImplementation(() => {})
  vi.spyOn(sdk, 'loadEditor').mockResolvedValue({ DocEditor: class {
    constructor(_id: string, config: Record<string, unknown>) { construct(); events = config.events as typeof events }
    destroyEditor() { destroy() }
  } })
})
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })

describe('在线文档保存边界', () => {
  it('records only successfully opened documents and requests server ordering', async () => {
    await render(); await wrapper!.get('select[aria-label="文档排序"]').setValue('name'); await flushPromises()
    expect(api.list).toHaveBeenLastCalledWith('huaxing', undefined, { sort: 'name' })
    await open(); events.onDocumentStateChange!({ data: false })
    vi.mocked(api.save).mockResolvedValue({ request_id: '', revision: 1 })
    await button('文档列表').trigger('click'); await flushPromises()
    await wrapper!.get('select[aria-label="文档排序"]').setValue('recent'); await flushPromises()
    expect(api.list).toHaveBeenLastCalledWith('huaxing', undefined, { sort: 'recent', recent_ids: 'd1' })
    authState.currentUser = { id: 'other', display_name: '其他用户', authorization_version: 1 }; await flushPromises()
    expect(api.list).toHaveBeenLastCalledWith('huaxing', undefined, { sort: 'recent', recent_ids: '' })
  })
  it('copies the confirmed durable revision and retries the same receipt after an uncertain result', async () => {
    vi.mocked(api.copy).mockRejectedValueOnce(new Error('连接中断')).mockResolvedValueOnce({ ...document(), id: 'copy' })
    await render(); await button('复制').trigger('click'); await flushPromises()
    expect(wrapper!.text()).toContain('复制已保存的版本 1')
    await wrapper!.get('#od-copy-title').setValue('月报副本')
    await wrapper!.get('form[aria-label="复制文档"]').trigger('submit'); await flushPromises()
    const request = vi.mocked(api.copy).mock.calls[0]![2]
    expect(request).toEqual({ request_id: expect.any(String), expected_revision: 1, title: '月报副本', folder_id: null })
    expect(canChangeFactory()).toBe(false)
    expect(wrapper!.get('#od-copy-title').attributes('disabled')).toBeDefined()
    await wrapper!.get('form[aria-label="复制文档"]').trigger('submit'); await flushPromises()
    expect(vi.mocked(api.copy).mock.calls[1]![2]).toEqual(request)
    expect(canChangeFactory()).toBe(true)
    expect(wrapper!.text()).toContain('仅自己可见')
  })
  it('renames in the editor without destroying the session or clearing unsaved changes', async () => {
    await render(); await open(); events.onDocumentStateChange!({ data: true }); await flushPromises()
    await button('重命名').trigger('click'); await wrapper!.get('#od-rename-title').setValue('十月汇总')
    await wrapper!.get('form[aria-label="重命名文件"]').trigger('submit'); await flushPromises()
    expect(wrapper!.get('.od-editor-title').text()).toContain('十月汇总.xlsx')
    expect(wrapper!.text()).toContain('有修改待存入系统')
    expect(destroy).not.toHaveBeenCalled()
    expect(api.save).not.toHaveBeenCalled()
  })
  it('keeps a durable rename visible and permits retrying editor title synchronization', async () => {
    vi.mocked(api.rename).mockResolvedValueOnce({ ...document(), title: '其他窗口的更新名称', title_sync_pending: true, operation_notice: '名称已保存，请重试同步名称' })
    await render(); await open(); await button('重命名').trigger('click')
    await wrapper!.get('#od-rename-title').setValue('新标题')
    await wrapper!.get('form[aria-label="重命名文件"]').trigger('submit'); await flushPromises()
    expect(wrapper!.get('.od-editor-title').text()).toContain('其他窗口的更新名称.xlsx')
    expect(button('重试同步名称')).toBeDefined()
    await wrapper!.get('form[aria-label="重命名文件"]').trigger('submit'); await flushPromises()
    expect(api.rename).toHaveBeenLastCalledWith('huaxing', 'd1', '其他窗口的更新名称', '其他窗口的更新名称', 1)
    expect(destroy).not.toHaveBeenCalled()
  })
  it('uses the current folder name as a rename precondition and keeps its selected id', async () => {
    await render(); await wrapper!.get('#od-folder-filter').setValue('folder-1'); await flushPromises()
    await button('文件夹改名').trigger('click'); await wrapper!.get('#od-folder-rename').setValue('新文件夹')
    await wrapper!.get('form[aria-label="重命名文件夹"]').trigger('submit'); await flushPromises()
    expect(api.renameFolder).toHaveBeenCalledWith('huaxing', 'folder-1', '新文件夹', '成品进出', 1)
    expect(wrapper!.get('#od-folder-filter').element).toHaveProperty('value', 'folder-1')
  })
  it('creates a folder over HTTP without randomUUID and sends an atomic versioned move', async () => {
    const secure = globalThis.crypto
    vi.stubGlobal('crypto', { getRandomValues: secure.getRandomValues.bind(secure) })
    await render()
    await button('新建文件夹').trigger('click')
    await wrapper!.get('#od-folder-name').setValue('月报')
    await wrapper!.get('form[aria-label="新建文件夹"]').trigger('submit'); await flushPromises()
    expect(api.createFolder).toHaveBeenCalledWith('huaxing', { id: expect.stringMatching(/^[a-f0-9-]{36}$/), name: '月报' })
    await wrapper!.get('input[type="checkbox"]').setValue(true)
    await wrapper!.get('#od-move-target').setValue('folder-1')
    await wrapper!.get('form[aria-label="文档归类"]').trigger('submit'); await flushPromises()
    expect(api.move).toHaveBeenCalledWith('huaxing', { request_id: expect.any(String), folder_id: 'folder-1', documents: [{ id: 'd1', expected_version: 0 }] })
    expect(wrapper!.text()).toContain('已完成 1 份文档的归类')
  })
  it('filters on the server and never selects a shared colleague document', async () => {
    vi.mocked(api.list).mockResolvedValue([document(), { ...document(), id: 'shared', access: 'edit' }])
    await render()
    expect(wrapper!.findAll('input[type="checkbox"]')).toHaveLength(1)
    await wrapper!.get('#od-folder-filter').setValue('folder-1'); await flushPromises()
    expect(api.list).toHaveBeenLastCalledWith('huaxing', 'folder-1')
    expect(wrapper!.text()).toContain('当前文件夹：成品进出')
  })
  it('retains the original batch across an uncertain response and blocks leaving', async () => {
    vi.mocked(api.move).mockRejectedValueOnce(new Error('连接中断')).mockResolvedValueOnce({ moved: 1 })
    await render(); await wrapper!.get('input[type="checkbox"]').setValue(true)
    await wrapper!.get('form[aria-label="文档归类"]').trigger('submit'); await flushPromises()
    const payload = vi.mocked(api.move).mock.calls[0]![1]
    expect(canChangeFactory()).toBe(false)
    expect(button('打开').attributes('disabled')).toBeDefined()
    await button('重试归类操作').trigger('click'); await flushPromises()
    expect(vi.mocked(api.move).mock.calls[1]![1]).toEqual(payload)
    expect(canChangeFactory()).toBe(true)
  })
  it('discards a previous identity folder response and selection', async () => {
    let resolve!: (value: { id: string; name: string; version: number }[]) => void
    vi.mocked(api.folders).mockImplementationOnce(() => new Promise(r => { resolve = r }))
    wrapper = mount(Workspace, { props: { factoryId: 'group' } }); await flushPromises()
    authState.currentUser.authorization_version++
    await flushPromises()
    resolve([{ id: 'old', name: '旧账号私密文件夹', version: 1 }]); await flushPromises()
    expect(wrapper.text()).not.toContain('旧账号私密文件夹')
  })
  it('keeps editing across an unchanged account refresh and clears on a real authorization change', async () => {
    await render(); await open(); events.onDocumentStateChange!({ data: true }); await flushPromises()
    authState.currentUser = { ...authState.currentUser }
    await flushPromises()
    expect(destroy).not.toHaveBeenCalled()
    expect(wrapper!.text()).toContain('有修改待存入系统')
    authState.currentUser = { ...authState.currentUser, authorization_version: 2 }
    await flushPromises()
    expect(destroy).toHaveBeenCalledOnce()
    expect(button('打开').attributes('disabled')).toBeUndefined()
  })
  it('shares group documents with named colleagues, defaulting to read only', async () => {
    wrapper = mount(Workspace, { props: { factoryId: 'group' } }); await flushPromises()
    expect(wrapper.text()).toContain('文件默认仅自己可见')
    await button('共享').trigger('click'); await flushPromises()
    expect(api.recipients).toHaveBeenCalledWith('group')
    expect(wrapper.get('[aria-label="新增共享权限"]').element).toHaveProperty('value', 'view')
    await wrapper.get('[aria-label="选择共享同事"]').setValue('viewer')
    await button('添加').trigger('click')
    await wrapper.get('[aria-label="选择共享同事"]').setValue('editor')
    await wrapper.get('[aria-label="新增共享权限"]').setValue('edit')
    await button('添加').trigger('click')
    expect(api.share).not.toHaveBeenCalled()
    await button('保存共享设置').trigger('click'); await flushPromises()
    expect(api.share).toHaveBeenCalledWith('group', 'd1', [
      { user_id: 'viewer', name: '同事甲', epoch: 1, access: 'view' },
      { user_id: 'editor', name: '同事乙', epoch: 1, access: 'edit' },
    ], 'acl-v1')
    expect(wrapper.text()).toContain('共享设置已保存')
    expect(wrapper.find('[aria-label="共享设置"]').exists()).toBe(false)
    expect(api.list).toHaveBeenCalledWith('group')
  })
  it('loads existing grants, changes permissions and removes a colleague', async () => {
    const shared = { ...document(), grants: [{ user_id: 'viewer', name: '同事甲', epoch: 1, access: 'view' as const }, { user_id: 'editor', name: '同事乙', epoch: 1, access: 'edit' as const }] }
    vi.mocked(api.detail).mockResolvedValue(shared)
    await render(); await button('共享').trigger('click'); await flushPromises()
    await wrapper!.get('.od-grants select').setValue('edit')
    await wrapper!.get('[aria-label="移除同事乙的共享"]').trigger('click')
    await button('保存共享设置').trigger('click'); await flushPromises()
    expect(api.share).toHaveBeenCalledWith('huaxing', 'd1', [{ user_id: 'viewer', name: '同事甲', epoch: 1, access: 'edit' }], 'acl-v1')
    expect(shared.grants).toHaveLength(2)
    expect(shared.grants[0]?.access).toBe('view')
  })
  it('keeps failed sharing drafts and locks sharing during active editing', async () => {
    await render(); await button('共享').trigger('click'); await flushPromises()
    await wrapper!.get('[aria-label="选择共享同事"]').setValue('viewer')
    await button('添加').trigger('click')
    vi.mocked(api.share).mockRejectedValue(new Error('保存失败'))
    await button('保存共享设置').trigger('click'); await flushPromises()
    expect(wrapper!.get('.od-grants').text()).toContain('同事甲')
    expect(wrapper!.get('[role="alert"]').text()).toContain('保存失败')
    await button('关闭').trigger('click')
    vi.mocked(api.detail).mockResolvedValue({ ...document(), editing: true })
    await button('共享').trigger('click'); await flushPromises()
    expect(button('保存共享设置').attributes('disabled')).toBeDefined()
    expect(wrapper!.text()).toContain('请所有人保存并关闭')
  })
  it('clears shared names and pending recipient responses at identity boundaries', async () => {
    await render(); await button('共享').trigger('click'); await flushPromises()
    authState.currentUser.authorization_version++
    await flushPromises()
    expect(wrapper!.find('[aria-label="共享设置"]').exists()).toBe(false)
    let resolve!: (value: Awaited<ReturnType<typeof api.recipients>>) => void
    vi.mocked(api.recipients).mockImplementation(() => new Promise(r => { resolve = r }))
    await button('共享').trigger('click'); await flushPromises()
    window.dispatchEvent(new Event('auth-session-boundary-changed'))
    resolve([{ id: 'viewer', display_name: '旧账号同事', department: '', epoch: 1 }]); await flushPromises()
    expect(wrapper!.text()).not.toContain('旧账号同事')
    expect(wrapper!.find('[aria-label="共享设置"]').exists()).toBe(false)
  })
  it.each(['view', 'edit'] as const)('does not offer sharing management to a %s recipient', async access => {
    vi.mocked(api.list).mockResolvedValue([{ ...document(), access, grants: undefined }])
    await render()
    expect(button('共享')).toBeUndefined()
    expect(button('重命名')).toBeUndefined()
    expect(button('复制')).toBeUndefined()
    expect(wrapper!.text()).toContain(access === 'view' ? '共享 · 只读' : '共享 · 可编辑')
  })
  it('renames a document with its current title and fixed extension', async () => {
    await render(); await button('重命名').trigger('click')
    expect(wrapper!.get('#od-rename-title').element).toHaveProperty('value', '公式试验')
    expect(wrapper!.get('[aria-label="重命名文件"]').text()).toContain('.xlsx')
    await wrapper!.get('#od-rename-title').setValue('十月汇总')
    await wrapper!.get('form').trigger('submit'); await flushPromises()
    expect(api.rename).toHaveBeenCalledWith('huaxing', 'd1', '十月汇总', '公式试验', 1)
    expect(wrapper!.get('.od-file-name').text()).toBe('十月汇总.xlsx')
    expect(wrapper!.text()).toContain('已重命名为「十月汇总.xlsx」')
    expect(wrapper!.find('form').exists()).toBe(false)
  })
  it('keeps failed rename input and cancels without sending another request', async () => {
    vi.mocked(api.rename).mockRejectedValue(new Error('请所有人保存并关闭文档后再重命名'))
    await render(); await button('重命名').trigger('click')
    await wrapper!.get('#od-rename-title').setValue('  ')
    expect(button('保存名称').attributes('disabled')).toBeDefined()
    await wrapper!.get('#od-rename-title').setValue('未保存的名称')
    await wrapper!.get('form').trigger('submit'); await flushPromises()
    expect(wrapper!.get('#od-rename-title').element).toHaveProperty('value', '未保存的名称')
    expect(wrapper!.get('#od-rename-error').text()).toContain('请所有人保存并关闭')
    await button('取消').trigger('click'); await flushPromises()
    expect(api.rename).toHaveBeenCalledOnce()
    expect(wrapper!.get('.od-file-name').text()).toBe('公式试验.xlsx')
  })
  it('discards a rename response after an account boundary', async () => {
    let resolve!: (value: OnlineDocument) => void
    vi.mocked(api.rename).mockImplementation(() => new Promise(r => { resolve = r }))
    await render(); await button('重命名').trigger('click')
    await wrapper!.get('#od-rename-title').setValue('旧账号文件')
    await wrapper!.get('form').trigger('submit')
    window.dispatchEvent(new Event('auth-session-boundary-changed'))
    resolve({ ...document(), title: '旧账号文件' }); await flushPromises()
    expect(wrapper!.find('form').exists()).toBe(false)
    expect(wrapper!.text()).not.toContain('旧账号文件')
  })
  it('uploads multipart fields without the shared JSON transform', async () => {
    const original = http.defaults.adapter
    let checked = false
    http.defaults.adapter = async config => {
      expect(config.data).toBeInstanceOf(FormData)
      expect(config.data.get('factory_id')).toBe('huaxing')
      expect(config.data.get('file').name).toBe('formula.xlsx')
      checked = true
      return { config, data: document(), status: 201, statusText: 'Created', headers: {} }
    }
    try { await api.upload('huaxing', new File(['xlsx'], 'formula.xlsx')) }
    finally { http.defaults.adapter = original }
    expect(checked).toBe(true)
  })
  it('waits for durable callback before clearing dirty state or downloading', async () => {
    await render(); await open(); events.onDocumentStateChange!({ data: true }); await flushPromises()
    expect(wrapper!.text()).toContain('有修改待存入系统')
    expect(canChangeFactory()).toBe(false)
    await button('下载').trigger('click'); await flushPromises()
    expect(api.save).not.toHaveBeenCalled()
    events.onDocumentStateChange!({ data: false })
    await vi.advanceTimersByTimeAsync(100); await flushPromises()
    expect(api.download).not.toHaveBeenCalled()
    expect(wrapper!.text()).toContain('正在保存到系统')
    vi.mocked(api.detail).mockResolvedValue({ ...document(), revision: 2, saved_request: 'request1' })
    await vi.advanceTimersByTimeAsync(1000); await flushPromises()
    expect(api.download).toHaveBeenCalledOnce()
    expect(wrapper!.text()).toContain('已保存到系统')
  })
  it('keeps the editor and unsaved state after a failed save', async () => {
    await render(); await open(); events.onDocumentStateChange!({ data: true })
    events.onDocumentStateChange!({ data: false })
    vi.mocked(api.save).mockRejectedValue(new Error('保存服务离线'))
    await button('保存到系统').trigger('click'); await flushPromises()
    expect(wrapper!.text()).toContain('保存服务离线')
    expect(wrapper!.text()).toContain('有修改待存入系统')
    expect(destroy).not.toHaveBeenCalled()
    await button('文档列表').trigger('click'); await flushPromises()
    expect(destroy).not.toHaveBeenCalled()
  })
  it('never constructs an editor after account boundary or unmount', async () => {
    let resolve!: (value: sdk.DocsApi) => void
    vi.mocked(sdk.loadEditor).mockImplementation(() => new Promise(r => { resolve = r }))
    await render(); await button('打开').trigger('click'); await flushPromises()
    window.dispatchEvent(new Event('auth-session-boundary-changed'))
    resolve({ DocEditor: class { constructor() { construct() } destroyEditor() {} } })
    await flushPromises()
    expect(construct).not.toHaveBeenCalled()
    expect(wrapper!.text()).not.toContain('公式试验')
  })
  it('shows service failure without offering enabled create actions', async () => {
    vi.mocked(api.list).mockRejectedValue(new Error('在线文档尚未启用'))
    await render()
    expect(wrapper!.text()).toContain('在线文档尚未启用')
    expect(button('Word 文档').attributes('disabled')).toBeDefined()
    expect(button('上传文档').attributes('disabled')).toBeDefined()
  })
  it('keeps a late history response from a previously selected file out of the new detail drawer', async () => {
    let resolve!: (value: Awaited<ReturnType<typeof api.history>>) => void
    vi.mocked(api.list).mockResolvedValue([document(), { ...document(), id: 'd2', title: '另一份文档' }])
    vi.mocked(api.history).mockImplementationOnce(() => new Promise(r => { resolve = r }))
    wrapper = mount(Workspace, { attachTo: globalThis.document.body, props: { factoryId: 'group' }, global: { stubs: { DialogPortal: { template: '<div><slot /></div>' } } } })
    await flushPromises()
    await button('详情').trigger('click'); await flushPromises()
    expect(wrapper.get('[role="dialog"] h2').text()).toBe('公式试验.xlsx · 历史版本')
    await button('关闭详情').trigger('click'); await flushPromises()
    await wrapper.findAll('button').filter(b => b.text() === '详情')[1]!.trigger('click'); await flushPromises()
    resolve({ items: [{ revision: 99, current: false, byte_size: 100, actor_id: 'owner', created_at: '' }], next_before: null })
    await flushPromises()
    expect(api.history).toHaveBeenLastCalledWith('group', 'd2', 0)
    expect(wrapper.get('[role="dialog"] h2').text()).toBe('另一份文档.xlsx · 历史版本')
    expect(wrapper.get('[role="dialog"]').text()).not.toContain('版本 99')
  })
})
