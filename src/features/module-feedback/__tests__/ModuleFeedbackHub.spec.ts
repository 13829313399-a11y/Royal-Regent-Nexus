import { DOMWrapper, flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ModuleFeedbackHub from '../ModuleFeedbackHub.vue'
import FeedbackAttachments from '../FeedbackAttachments.vue'
import type { FeedbackCapabilities, FeedbackDetail } from '@/api/moduleFeedback'

const api = vi.hoisted(() => ({ capabilities: vi.fn(), list: vi.fn(), detail: vi.fn(), read: vi.fn(), create: vi.fn(), reply: vi.fn() }))
const actor = vi.hoisted(() => ({ currentUser: { id: 'reporter' } }))
vi.mock('@/api/moduleFeedback', () => ({ moduleFeedbackApi: api, feedbackAttachmentUrl: () => '/api/test-attachment' }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => actor }))

const caps: FeedbackCapabilities = { can_submit: true, can_manage: false, can_link_order: true, max_files: 5, max_file_bytes: 10485760, max_total_bytes: 26214400, allowed_extensions: ['.png'], material_options: ['screenshot', 'steps', 'expected_result', 'original_file', 'order_reference'] }
function ticket(overrides: Partial<FeedbackDetail> = {}): FeedbackDetail {
  return { id: 'ticket-1', factory_id: 'huaxing', module: 'customer-order-center', title: '装箱数识别有误', category: 'bug', emoji: '🐞', status: 'submitted', author_id: 'reporter', author_name: '跟客用户', assigned_name: '', context: { page: '预览与确认' }, requested_materials: [], provided_materials: [], release_note: '', revision: 1, created_at: '2026-10-05T02:00:00Z', updated_at: '2026-10-05T02:00:00Z', unread: false, messages: [{ id: 'message-1', actor_name: '跟客用户', actor_kind: 'user', body: '这条订单装箱数应该是24', action: 'create', created_at: '2026-10-05T02:00:00Z', revision: 1, attachments: [], requested_materials: [], provided_materials: [], release_note: '' }], ...overrides }
}
let wrapper: VueWrapper<InstanceType<typeof ModuleFeedbackHub>>
const body = () => new DOMWrapper(document.body)
function button(text: string) { const found = body().findAll('button').find(item => item.text() === text); if (!found) throw new Error(`Button missing: ${text}`); return found }
async function start() {
  wrapper = mount(ModuleFeedbackHub, { props: { factoryId: 'huaxing', factoryName: '华兴', active: true }, attachTo: document.body })
  await flushPromises()
}
beforeEach(() => {
  vi.clearAllMocks(); actor.currentUser.id = 'reporter'
  api.capabilities.mockResolvedValue({ ...caps })
  api.list.mockResolvedValue({ items: [ticket()], total: 1, unread_count: 0, page: 1, page_size: 20 })
  api.detail.mockResolvedValue(ticket())
  api.read.mockResolvedValue({ through_revision: 1 })
  api.create.mockResolvedValue(ticket())
  api.reply.mockResolvedValue(ticket({ revision: 2 }))
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
})
afterEach(() => { wrapper?.unmount(); document.body.innerHTML = ''; vi.unstubAllGlobals() })

describe('module feedback pilot', () => {
  it('lets a confirmed employee without order read access report their own problem without automatic order data', async () => {
    api.capabilities.mockResolvedValue({ ...caps, can_link_order: false })
    await start()
    wrapper.vm.openComposer({ page: '订单详情', section: 'ledger', order_id: 'private-order', order_reference: 'PRIVATE-PO', customer_code: 'private-customer', product_no: 'private-product', file_names: ['private-file.xlsx'], error_message: 'private data' })
    await flushPromises()
    expect(body().text()).not.toContain('PRIVATE-PO')
    expect(body().text()).not.toContain('需要客户订单查看权限')
    await body().get('input[placeholder^="例如：BuzzBee"]').setValue('无法使用订单功能')
    await body().get('textarea[placeholder^="你做了什么"]').setValue('希望核对我的订单权限')
    await button('提交反馈').trigger('click'); await flushPromises()
    expect(api.create.mock.calls[0]![0]).toMatchObject({ body: '希望核对我的订单权限', context: { page: '订单详情', section: 'ledger' } })
    expect(api.create.mock.calls[0]![0].context.order_id).toBeUndefined()
    expect(api.create.mock.calls[0]![0].context.customer_code).toBeUndefined()
    expect(api.create.mock.calls[0]![0].context.file_names).toBeUndefined()
  })
  it('explains factory confirmation or feedback restrictions without requiring business data access', async () => {
    api.capabilities.mockResolvedValue({ ...caps, can_submit: false, can_link_order: false })
    await start()
    expect(wrapper.text()).toContain('请确认员工厂区归属已审核')
    expect(wrapper.text()).not.toContain('需要客户订单查看权限')
    expect(button('新建反馈').attributes('disabled')).toBeDefined()
  })
  it('hides revoked order context in the conversation and open draft while preserving a reply draft', async () => {
    api.detail.mockResolvedValue(ticket({ context: { page: '订单详情', order_id: 'line-1', order_reference: 'PRIVATE-PO' } }))
    await start(); await wrapper.get('.feedback-hub__ticket').trigger('click'); await flushPromises()
    await wrapper.get('.feedback-reply textarea').setValue('正在填写的补充说明')
    wrapper.vm.openComposer({ page: '订单详情', order_id: 'line-1', order_reference: 'PRIVATE-PO' }); await flushPromises()
    api.capabilities.mockResolvedValue({ ...caps, can_link_order: false })
    api.detail.mockResolvedValue(ticket({ context: { page: '订单详情', order_id: '', order_reference: '' } }))
    await wrapper.get('button[aria-label="刷新反馈"]').trigger('click'); await flushPromises()
    expect(body().text()).not.toContain('PRIVATE-PO')
    expect((wrapper.get('.feedback-reply textarea').element as HTMLTextAreaElement).value).toBe('正在填写的补充说明')
  })
  it('retains the exact uncertain create request after permission changes and prepares a safe fresh request only after confirmed rejection', async () => {
    api.create.mockRejectedValueOnce(new Error('网络中断'))
    await start()
    wrapper.vm.openComposer({ page: '订单详情', order_id: 'line-1', order_reference: 'PRIVATE-PO' }); await flushPromises()
    await body().get('input[placeholder^="例如：BuzzBee"]').setValue('订单关联问题')
    await body().get('textarea[placeholder^="你做了什么"]').setValue('请协助核查问题')
    await button('提交反馈').trigger('click'); await flushPromises()
    const original = api.create.mock.calls[0]![0]
    api.capabilities.mockResolvedValue({ ...caps, can_link_order: false })
    await wrapper.get('button[aria-label="刷新反馈"]').trigger('click'); await flushPromises()
    expect(body().text()).not.toContain('PRIVATE-PO')
    api.create.mockRejectedValueOnce(Object.assign(new Error('关联订单权限已撤销'), { isAxiosError: true, response: { status: 403 } }))
    await button('提交反馈').trigger('click'); await flushPromises()
    expect(api.create.mock.calls[1]![0]).toEqual(original)
    await button('提交反馈').trigger('click'); await flushPromises()
    const fresh = api.create.mock.calls[2]![0]
    expect(fresh.client_request_id).not.toBe(original.client_request_id)
    expect(fresh.context.order_id).toBeUndefined()
  })
  it('shows only user controls for an ordinary reporter and reads only the displayed revision', async () => {
    await start()
    expect(wrapper.text()).not.toContain('开发者处理')
    expect(api.read).not.toHaveBeenCalled()
    await wrapper.get('.feedback-hub__ticket').trigger('click'); await flushPromises()
    expect(api.read).toHaveBeenCalledWith('ticket-1', 'huaxing', 1)
    expect(wrapper.text()).not.toContain('快捷回复')
    expect(wrapper.text()).toContain('这条订单装箱数应该是24')
  })
  it('submits the chosen emotion and frozen order context, retaining idempotency on a network retry', async () => {
    api.create.mockRejectedValueOnce(new Error('网络暂时断开'))
    await start()
    const context = { page: '订单详情', order_id: 'line-1', order_reference: 'PO-24' }
    wrapper.vm.openComposer(context); await flushPromises()
    context.order_reference = 'changed-after-open'
    await body().get('input[placeholder^="例如：BuzzBee"]').setValue('装箱数量错误')
    await body().get('textarea[placeholder^="你做了什么"]').setValue('实际24，识别成12')
    await button('🐢太慢').trigger('click')
    await button('提交反馈').trigger('click'); await flushPromises()
    expect(body().text()).toContain('网络暂时断开')
    const first = api.create.mock.calls[0]![0]
    expect(first).toMatchObject({ factory_id: 'huaxing', emoji: '🐢', context: { order_id: 'line-1', order_reference: 'PO-24' } })
    await button('提交反馈').trigger('click'); await flushPromises()
    expect(api.create.mock.calls[1]![0].client_request_id).toBe(first.client_request_id)
    expect(wrapper.emitted('navigate')).toHaveLength(1)
  })
  it('requires a deployed release note before the developer can invite verification', async () => {
    actor.currentUser.id = 'developer'
    api.capabilities.mockResolvedValue({ ...caps, can_manage: true })
    await start(); await button('开发者处理').trigger('click'); await flushPromises()
    await wrapper.get('.feedback-hub__ticket').trigger('click'); await flushPromises()
    await button('修复上线，邀请验证').trigger('click')
    expect(button('发送回复').attributes('disabled')).toBeDefined()
    await wrapper.get('input[placeholder^="说明已经"]').setValue('测试环境 v1 已修复装箱数')
    await button('发送回复').trigger('click'); await flushPromises()
    expect(api.reply).toHaveBeenCalledWith('ticket-1', 'huaxing', expect.objectContaining({ action: 'ready', expected_revision: 1, release_note: '测试环境 v1 已修复装箱数' }), [])
  })
  it('keeps the user response after a concurrent update and submits against the refreshed revision', async () => {
    api.reply.mockRejectedValueOnce(Object.assign(new Error('反馈已有新回复'), { isAxiosError: true, response: { status: 409 } }))
    await start(); await wrapper.get('.feedback-hub__ticket').trigger('click'); await flushPromises()
    await wrapper.get('.feedback-reply textarea').setValue('补充说明：点击保存后出现错误')
    await button('发送回复').trigger('click'); await flushPromises()
    expect((wrapper.get('.feedback-reply textarea').element as HTMLTextAreaElement).value).toContain('补充说明')
    api.detail.mockResolvedValue(ticket({ revision: 3 }))
    await button('刷新对话').trigger('click'); await flushPromises()
    await button('发送回复').trigger('click'); await flushPromises()
    expect(api.reply.mock.calls[1]![2].expected_revision).toBe(3)
  })
  it('replays an uncertain reply with the original request and revision after refreshing', async () => {
    api.reply.mockRejectedValueOnce(new Error('连接中断'))
    await start(); await wrapper.get('.feedback-hub__ticket').trigger('click'); await flushPromises()
    await wrapper.get('.feedback-reply textarea').setValue('网络中断前已经发送的补充说明')
    await button('发送回复').trigger('click'); await flushPromises()
    const first = api.reply.mock.calls[0]![2]
    api.detail.mockResolvedValue(ticket({ revision: 2 }))
    await button('刷新对话').trigger('click'); await flushPromises()
    await button('发送回复').trigger('click'); await flushPromises()
    expect(api.reply.mock.calls[1]![2]).toEqual(first)
    expect(first.expected_revision).toBe(1)
  })
  it('allows an attachment-only response to a request for materials', async () => {
    api.detail.mockResolvedValue(ticket({ status: 'needs_info', requested_materials: ['screenshot'] }))
    await start(); await wrapper.get('.feedback-hub__ticket').trigger('click'); await flushPromises()
    const file = new File(['test screenshot'], 'screen.png', { type: 'image/png' })
    vi.stubGlobal('URL', { createObjectURL: () => 'blob:test', revokeObjectURL: vi.fn() })
    wrapper.getComponent(FeedbackAttachments).vm.$emit('update:modelValue', [file]); await flushPromises()
    await wrapper.get('.feedback-reply input[type="checkbox"]').setValue(true)
    expect(wrapper.get('.feedback-reply textarea').attributes('required')).toBeUndefined()
    await button('发送回复').trigger('click'); await flushPromises()
    expect(api.reply).toHaveBeenCalledWith('ticket-1', 'huaxing', expect.objectContaining({ body: '', action: 'reply', provided_materials: ['screenshot'] }), [file])
  })
  it('does not read a detail response that arrives after navigating away', async () => {
    let resolveDetail!: (value: FeedbackDetail) => void
    api.detail.mockImplementationOnce(() => new Promise<FeedbackDetail>(resolve => { resolveDetail = resolve }))
    await start(); await wrapper.get('.feedback-hub__ticket').trigger('click')
    await wrapper.setProps({ active: false })
    resolveDetail(ticket()); await flushPromises()
    expect(api.read).not.toHaveBeenCalled()
  })
  it('lets only the author confirm a fix and displays requested materials', async () => {
    api.detail.mockResolvedValue(ticket({ status: 'awaiting_verification', requested_materials: ['screenshot'], provided_materials: ['screenshot'] }))
    await start(); await wrapper.get('.feedback-hub__ticket').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('用户已补充')
    await button('问题已解决').trigger('click')
    expect(api.reply).not.toHaveBeenCalled()
    await button('发送回复').trigger('click'); await flushPromises()
    expect(api.reply.mock.calls[0]![2].action).toBe('resolve')
  })
  it('discards stale detail responses when the factory changes', async () => {
    let resolveOld!: (value: FeedbackDetail) => void
    api.detail.mockImplementationOnce(() => new Promise<FeedbackDetail>(resolve => { resolveOld = resolve }))
    await start(); await wrapper.get('.feedback-hub__ticket').trigger('click')
    api.list.mockResolvedValue({ items: [], total: 0, unread_count: 0, page: 1, page_size: 20 })
    await wrapper.setProps({ factoryId: 'huadeng', factoryName: '华登' }); await flushPromises()
    resolveOld(ticket()); await flushPromises()
    expect(wrapper.text()).not.toContain('这条订单装箱数应该是24')
    expect(api.read).not.toHaveBeenCalled()
  })
})
