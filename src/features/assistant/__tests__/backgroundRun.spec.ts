import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, nextTick, reactive } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { useAssistantStore } from '@/stores/assistant'
import AssistantHost from '../AssistantHost.vue'
import { assistantApi } from '../api'
import type { Capabilities, SendPayload } from '../types'

const mocks = vi.hoisted(() => ({
  route: { name: 'dashboard', query: {} as Record<string, string>, meta: { title: '合成页面' } },
  auth: { currentUser: { id: 'test', identity: { employment_epoch: 1, effective_context_key: 'same' } }, authorizationVersion: 1 },
  app: { activeFactoryId: 'group' },
}))
vi.mock('vue-router', () => ({ useRoute: () => mocks.route }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => mocks.auth }))
vi.mock('@/stores/app', () => ({ useAppStore: () => mocks.app }))
const PanelStub = defineComponent({ props: ['mode'], template: '<section data-test="panel" v-show="mode !== \'edge\'"></section>' })
const input: Omit<SendPayload, 'client_request_id'> = { text: '合成问题', attachment_ids: [], intent: 'chat', profile_id: 'default', thinking: 'off', web_search: 'off', page_context: { module_id: 'portal', route_name: 'dashboard', factory_id: 'group' } }
const session = { id: 's1', title: '合成会话', revision: 1, deletion_state: 'active', created_at: 1, updated_at: 1 }
let host: ReturnType<typeof mount>, stream: ReadableStreamDefaultController<Uint8Array>, running: Promise<void> | undefined, seq: number
const launcher = () => document.querySelector<HTMLButtonElement>('.yl-launcher')!
async function event(name: string, data: Record<string, unknown> = {}) {
  stream.enqueue(new TextEncoder().encode(`event: ${name}\ndata: ${JSON.stringify({ run_id: 'r1', seq: ++seq, ...data })}\n\n`))
  await flushPromises()
}
async function start(page = input.page_context) {
  const store = useAssistantStore()
  store.selectedId = session.id
  running = store.submit({ ...input, page_context: page })
  await flushPromises()
  await event('response.delta', { channel: 'answer', text: '第一段。' })
  return store
}
beforeEach(async () => {
  vi.restoreAllMocks(); setActivePinia(createPinia()); seq = 0; running = undefined
  mocks.route = reactive({ name: 'dashboard', query: {}, meta: { title: '合成页面' } })
  mocks.auth = reactive({ currentUser: { id: 'test', identity: { employment_epoch: 1, effective_context_key: 'same' } }, authorizationVersion: 1 })
  mocks.app = reactive({ activeFactoryId: 'group' })
  Object.defineProperty(document, 'hidden', { configurable: true, value: false })
  vi.spyOn(assistantApi, 'capabilities').mockResolvedValue({ enabled: true } as Capabilities)
  vi.spyOn(assistantApi, 'send').mockResolvedValue(new Response(new ReadableStream({ start(c) { stream = c } }), { headers: { 'Content-Type': 'text/event-stream' } }))
  vi.spyOn(assistantApi, 'cancel').mockResolvedValue({ state: 'answering' })
  vi.spyOn(assistantApi, 'sessions').mockResolvedValue({ items: [session], next_cursor: null })
  vi.spyOn(assistantApi, 'messages').mockImplementation(async () => ({ session, items: [...useAssistantStore().messages], next_cursor: null, active_run_id: null }))
  host = mount(AssistantHost, { attachTo: document.body, global: { stubs: { Panel: PanelStub } } })
  await flushPromises(); launcher().click(); await flushPromises()
})
afterEach(async () => {
  host.unmount(); stream.close(); await running; document.body.innerHTML = ''
  delete (document as unknown as Record<string, unknown>).hidden
})

describe('collapsed assistant generation', () => {
  it('continues the same stream after collapse and same-factory navigation', async () => {
    const store = await start()
    launcher().click(); await nextTick()
    expect(launcher().textContent).toContain('生成中')
    mocks.route.name = 'modules-department'; await flushPromises()
    expect(assistantApi.cancel).not.toHaveBeenCalled()
    expect(store.currentRun?.controller.signal.aborted).toBe(false)
    await event('response.delta', { channel: 'answer', text: '第二段。' })
    await event('run.completed')
    expect(store.currentRun?.state).toBe('completed')
    expect(store.messages.at(-1)?.content_parts.map(p => p.text).join('')).toBe('第一段。第二段。')
    expect(assistantApi.send).toHaveBeenCalledTimes(1)
    expect(store.currentRun?.payload.page_context?.route_name).toBe('dashboard')
    expect(launcher().textContent).toContain('已完成')
    expect(launcher().getAttribute('aria-expanded')).toBe('false')
    launcher().click(); await nextTick()
    expect(launcher().textContent).toContain('曜灵')
    launcher().click(); await nextTick()
    expect(launcher().textContent).not.toContain('已完成')
  })
  it('does not cancel when navigating to a page without registered help', async () => {
    await start(); launcher().click(); await nextTick()
    mocks.route.name = 'unregistered-business-page'; await flushPromises()
    expect(assistantApi.cancel).not.toHaveBeenCalled()
  })
  it('does not cancel on ordinary authentication refresh or page visibility changes', async () => {
    await start(); launcher().click(); await nextTick()
    mocks.auth.currentUser = { ...mocks.auth.currentUser, identity: { ...mocks.auth.currentUser.identity } }
    Object.defineProperty(document, 'hidden', { configurable: true, value: true })
    document.dispatchEvent(new Event('visibilitychange')); await flushPromises()
    expect(assistantApi.cancel).not.toHaveBeenCalled()
  })
  it('still cancels context-bound work on a real factory or authorization change', async () => {
    await start(); mocks.app.activeFactoryId = 'huaxing'; await flushPromises()
    expect(assistantApi.cancel).toHaveBeenCalledWith('r1')
    vi.mocked(assistantApi.cancel).mockClear()
    mocks.auth.authorizationVersion++; await flushPromises()
    expect(assistantApi.cancel).toHaveBeenCalledWith('r1')
  })
  it('keeps a context-free conversation running across factory changes', async () => {
    await start(null); mocks.app.activeFactoryId = 'huaxing'; await flushPromises()
    expect(assistantApi.cancel).not.toHaveBeenCalled()
  })
  it('keeps streaming when only collapsed, and still supports an explicit stop', async () => {
    const store = await start(); launcher().click(); await nextTick()
    expect(assistantApi.cancel).not.toHaveBeenCalled()
    await event('response.delta', { channel: 'answer', text: '继续生成。' })
    expect(store.busy).toBe(true)
    await store.stop()
    expect(assistantApi.cancel).toHaveBeenCalledTimes(1)
    await event('run.cancelled')
    expect(launcher().textContent).toContain('已停止')
    expect(store.messages.at(-1)?.content_parts.map(p => p.text).join('')).toBe('第一段。继续生成。')
  })
  it.each(['failed', 'interrupted'])('shows a %s result without silently retrying', async state => {
    await start(); launcher().click(); await nextTick()
    await event(`run.${state}`)
    expect(launcher().textContent).toContain('需查看')
    expect(launcher().getAttribute('aria-label')).toContain(state === 'failed' ? '本次未完成' : '连接中断')
    expect(assistantApi.send).toHaveBeenCalledTimes(1)
  })
  it('retains a completed badge while the document is hidden, then clears it when read', async () => {
    await start()
    Object.defineProperty(document, 'hidden', { configurable: true, value: true })
    document.dispatchEvent(new Event('visibilitychange')); await nextTick()
    await event('run.completed')
    expect(launcher().textContent).toContain('已完成')
    Object.defineProperty(document, 'hidden', { configurable: true, value: false })
    document.dispatchEvent(new Event('visibilitychange')); await nextTick()
    expect(launcher().textContent).toContain('曜灵')
  })
  it('still clears private progress and aborts the old stream on identity change', async () => {
    const store = await start(), signal = store.currentRun!.controller.signal
    launcher().click(); await nextTick()
    mocks.auth.currentUser.identity.employment_epoch++; await flushPromises()
    expect(signal.aborted).toBe(true)
    expect(store.messages).toEqual([])
    expect(store.runs).toEqual({})
    expect(launcher().textContent).toContain('曜灵')
  })
})
