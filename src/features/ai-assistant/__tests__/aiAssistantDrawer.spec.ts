import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { flushPromises, mount, shallowMount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  getAICapabilities: vi.fn(),
  streamAIResponse: vi.fn(),
}))

vi.mock('@/api/ai', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/api/ai')>(),
  getAICapabilities: apiMocks.getAICapabilities,
  streamAIResponse: apiMocks.streamAIResponse,
}))

import type { AuthMeResponse } from '@/api/auth'
import { AIClientError } from '@/api/ai'
import AppShell from '@/components/layout/AppShell.vue'
import { acquireBodyScrollLock } from '@/lib/bodyScrollLock'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import AiAssistantDrawer from '../AiAssistantDrawer.vue'
import { useAIAssistantStore } from '../store'
import aiStoreSource from '../store.ts?raw'
import type { AICapabilities, AIStreamEnvelope } from '../types'

const usableCapabilities: AICapabilities = {
  enabled: true,
  available: true,
  provider: 'test',
  model: 'test',
  streaming: true,
  vision_enabled: false,
  conversation_persistence: false,
  tool_groups: ['module_help'],
  pilot_access: { granted: true, status: 'GRANTED', read_only: true },
}

function event(sequence: number, type: string, payload: Record<string, unknown> = {}): AIStreamEnvelope {
  return {
    schema_version: '1',
    request_id: 'web-drawer-test',
    sequence,
    type,
    timestamp: `2026-08-11T00:00:0${sequence}Z`,
    payload,
  }
}

function createTestRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'dashboard', component: { template: '<div />' }, meta: { requiresAuth: true } },
      { path: '/login', name: 'login', component: { template: '<div />' }, meta: { requiresAuth: false, fullPage: true } },
      { path: '/register', name: 'register', component: { template: '<div />' }, meta: { requiresAuth: false, fullPage: true } },
      { path: '/change-password', name: 'change-password', component: { template: '<div />' }, meta: { requiresAuth: true, fullPage: true } },
      { path: '/forbidden', name: 'forbidden', component: { template: '<div />' }, meta: { requiresAuth: true, fullPage: true } },
      {
        path: '/modules/production/injection-scheduling',
        name: 'injection-scheduling-v2',
        component: { template: '<div data-testid="scheduling-page" />' },
        meta: { requiresAuth: true, fullPage: true },
      },
    ],
  })
}

function authenticate(pinia: Pinia) {
  const auth = useAuthStore(pinia)
  auth.currentUser = { force_password_change: false } as AuthMeResponse
  auth.isAuthenticated = true
  auth.hasLoadedSession = true
  auth.sessionVersion = 1
  return auth
}

async function mountDrawer(
  capabilities: AICapabilities = usableCapabilities,
  path = '/modules/production/injection-scheduling?factory=huaxing',
) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = createTestRouter()
  await router.push(path)
  await router.isReady()
  authenticate(pinia)
  useAppStore(pinia).activeFactoryId = 'huaxing'
  apiMocks.getAICapabilities.mockResolvedValue(capabilities)
  const wrapper = mount(AiAssistantDrawer, {
    attachTo: document.body,
    global: { plugins: [pinia, router] },
  })
  await flushPromises()
  return { wrapper, pinia, router }
}

function triggerButton() {
  return document.querySelector<HTMLButtonElement>('#ai-assistant-trigger')
}

async function openDrawer() {
  triggerButton()?.click()
  await flushPromises()
}

function inputMessage(value: string) {
  const textarea = document.querySelector<HTMLTextAreaElement>('#ai-assistant-message')
  if (!textarea) throw new Error('AI composer is not mounted')
  textarea.value = value
  textarea.dispatchEvent(new Event('input', { bubbles: true }))
  textarea.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
  return textarea
}

beforeEach(() => {
  apiMocks.getAICapabilities.mockReset()
  apiMocks.streamAIResponse.mockReset()
  apiMocks.streamAIResponse.mockImplementation(async (options) => {
    options.onEvent(event(1, 'message.delta', { delta: '纯文本帮助' }))
    options.onEvent(event(2, 'response.completed'))
    return event(2, 'response.completed')
  })
  vi.stubGlobal('matchMedia', vi.fn(() => ({
    matches: false,
    media: '',
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })))
  Object.defineProperty(HTMLElement.prototype, 'scrollTo', {
    configurable: true,
    value: vi.fn(),
  })
})

afterEach(() => {
  document.body.innerHTML = ''
  document.body.style.overflow = ''
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('global AI assistant drawer', () => {
  it('shows on an authenticated fullPage business route and AppShell keeps the hook beside RouterView', async () => {
    const { wrapper, pinia, router } = await mountDrawer()
    expect(triggerButton()).not.toBeNull()
    await openDrawer()
    expect(document.querySelector('[data-ai-pilot-status]')?.textContent).toContain('Pilot 已准入 · 只读模式')
    expect(document.querySelector('[data-ai-pilot-status]')?.textContent).toContain('AI 不会直接写入业务数据')

    const shell = shallowMount(AppShell, {
      global: {
        plugins: [pinia, router],
        stubs: {
          RouterView: { template: '<div data-testid="full-page-view" />' },
          SidebarNav: true,
          TopBar: true,
          AiAssistantDrawer: { template: '<div data-testid="ai-shell-hook" />' },
        },
      },
    })
    expect(shell.find('[data-testid="full-page-view"]').exists()).toBe(true)
    expect(shell.find('[data-testid="ai-shell-hook"]').exists()).toBe(true)
    expect(shell.find('.app-shell').exists()).toBe(false)
    shell.unmount()
    wrapper.unmount()
  })

  it.each([
    ['disabled', { ...usableCapabilities, enabled: false }],
    ['unavailable', { ...usableCapabilities, available: false }],
    ['non-streaming', { ...usableCapabilities, streaming: false }],
    ['pilot denied', { ...usableCapabilities, pilot_access: { granted: false, status: 'DISABLED' as const, read_only: true } }],
    ['TLS required', { ...usableCapabilities, pilot_access: { granted: false, status: 'TLS_REQUIRED' as const, read_only: true } }],
    ['control required', { ...usableCapabilities, pilot_access: { granted: false, status: 'CONTROL_REQUIRED' as const, read_only: true } }],
    ['provider required', { ...usableCapabilities, pilot_access: { granted: false, status: 'PROVIDER_REQUIRED' as const, read_only: true } }],
    ['not read-only', { ...usableCapabilities, pilot_access: { granted: true, status: 'GRANTED' as const, read_only: false } }],
  ])('does not expose the trigger when capabilities are %s', async (_label, capabilities) => {
    const { wrapper } = await mountDrawer(capabilities)
    expect(triggerButton()).toBeNull()
    wrapper.unmount()
  })

  it('fails closed when the Pilot contract is missing or has an unknown status', async () => {
    const missingPilot = { ...usableCapabilities } as Partial<AICapabilities>
    delete missingPilot.pilot_access
    const first = await mountDrawer(missingPilot as AICapabilities)
    expect(triggerButton()).toBeNull()
    first.wrapper.unmount()

    const second = await mountDrawer({
      ...usableCapabilities,
      pilot_access: { granted: true, status: 'UNKNOWN', read_only: true },
    })
    expect(triggerButton()).toBeNull()
    second.wrapper.unmount()
  })

  it('revalidates capabilities before opening and removes a stale granted entry immediately', async () => {
    const { wrapper } = await mountDrawer()
    expect(triggerButton()).not.toBeNull()
    apiMocks.getAICapabilities.mockResolvedValue({
      ...usableCapabilities,
      enabled: false,
      pilot_access: { granted: false, status: 'DISABLED', read_only: true },
    })

    triggerButton()?.click()
    await flushPromises()
    expect(document.querySelector('#ai-assistant-drawer')).toBeNull()
    expect(triggerButton()).toBeNull()
    wrapper.unmount()
  })

  it('hides on an expected capability 403 without changing sessionVersion or probing again', async () => {
    const { wrapper, pinia } = await mountDrawer()
    const auth = useAuthStore(pinia)
    const sessionVersion = auth.sessionVersion
    apiMocks.getAICapabilities.mockRejectedValue(new AIClientError('当前账号未加入 AI Pilot。', {
      code: 'AI_PILOT_ACCESS_DENIED',
      status: 403,
      retryable: false,
    }))

    triggerButton()?.click()
    await flushPromises()
    await flushPromises()

    expect(useAIAssistantStore(pinia).capabilities).toBeNull()
    expect(triggerButton()).toBeNull()
    expect(auth.sessionVersion).toBe(sessionVersion)
    expect(apiMocks.getAICapabilities).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('hides on login, registration, password-change and forbidden routes', async () => {
    const { wrapper, router } = await mountDrawer()
    for (const path of ['/login', '/register', '/change-password', '/forbidden']) {
      await router.push(path)
      await flushPromises()
      expect(triggerButton()).toBeNull()
    }
    wrapper.unmount()
  })

  it('stays hidden until the authenticated user has completed forced password change', async () => {
    const { wrapper, pinia } = await mountDrawer()
    const auth = useAuthStore(pinia)
    if (!auth.currentUser) throw new Error('test session was not initialized')
    auth.currentUser.force_password_change = true
    auth.sessionVersion += 1
    await flushPromises()
    expect(triggerButton()).toBeNull()
    wrapper.unmount()
  })

  it('focuses the composer, traps Tab in the dialog, and restores focus after Escape', async () => {
    const { wrapper } = await mountDrawer()
    expect(triggerButton()?.className).toContain('focus-visible:outline')
    await openDrawer()
    const dialog = document.querySelector<HTMLElement>('#ai-assistant-drawer')
    const textarea = document.querySelector<HTMLTextAreaElement>('#ai-assistant-message')
    const close = document.querySelector<HTMLButtonElement>('button[aria-label="关闭 AI 助手并清空对话"]')
    expect(dialog?.getAttribute('role')).toBe('dialog')
    expect(document.querySelector('[role="log"]')?.getAttribute('aria-live')).toBe('polite')
    expect(document.querySelector('input[type="file"]')).toBeNull()
    expect(dialog?.textContent).toContain('当前仅支持文字，不上传附件')
    expect(document.activeElement).toBe(textarea)

    textarea?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }))
    expect(document.activeElement).toBe(close)
    close?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true }))
    expect(document.activeElement).toBe(textarea)

    const escapedToDocument = vi.fn()
    document.addEventListener('keydown', escapedToDocument)
    textarea?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()
    expect(escapedToDocument).not.toHaveBeenCalled()
    document.removeEventListener('keydown', escapedToDocument)
    expect(document.querySelector('#ai-assistant-drawer')).toBeNull()
    expect(document.activeElement).toBe(triggerButton())
    wrapper.unmount()
  })

  it('does not unlock body scrolling while another overlay still owns a lock', async () => {
    document.body.style.overflow = 'clip'
    const releaseOtherOverlay = acquireBodyScrollLock()
    const { wrapper } = await mountDrawer()
    try {
      await openDrawer()
      expect(document.body.style.overflow).toBe('hidden')

      document.querySelector<HTMLButtonElement>('button[aria-label="关闭 AI 助手并清空对话"]')?.click()
      await flushPromises()
      expect(document.body.style.overflow).toBe('hidden')
    } finally {
      wrapper.unmount()
      releaseOtherOverlay()
    }
    expect(document.body.style.overflow).toBe('clip')
  })

  it('rebuilds route/factory context at each send and renders hostile model text as plain text', async () => {
    apiMocks.streamAIResponse.mockImplementation(async (options) => {
      options.onEvent(event(1, 'message.delta', { delta: '<img src=x onerror=alert(1)> **raw**' }))
      options.onEvent(event(2, 'response.completed'))
      return event(2, 'response.completed')
    })
    const { wrapper, router } = await mountDrawer()
    await openDrawer()
    inputMessage('第一次')
    await flushPromises()
    expect(document.querySelector('#ai-assistant-drawer img')).toBeNull()
    expect(document.querySelector('#ai-assistant-drawer')?.textContent).toContain('<img src=x onerror=alert(1)> **raw**')

    await router.push('/modules/production/injection-scheduling?factory=huakang-b')
    await flushPromises()
    inputMessage('第二次')
    await flushPromises()

    expect(apiMocks.streamAIResponse).toHaveBeenCalledTimes(2)
    expect(apiMocks.streamAIResponse.mock.calls[0]?.[0].pageContext.factory_id).toBe('huaxing')
    expect(apiMocks.streamAIResponse.mock.calls[1]?.[0].pageContext.factory_id).toBe('huakang-b')
    wrapper.unmount()
  })

  it('renders each delayed delta while the POST stream is still open', async () => {
    let pushEvent: ((streamEvent: AIStreamEnvelope) => void) | undefined
    let complete: ((streamEvent: AIStreamEnvelope) => void) | undefined
    apiMocks.streamAIResponse.mockImplementationOnce((options) => {
      pushEvent = options.onEvent
      return new Promise<AIStreamEnvelope>((resolve) => {
        complete = resolve
      })
    })
    const { wrapper } = await mountDrawer()
    await openDrawer()
    inputMessage('逐段显示')
    await flushPromises()

    pushEvent?.(event(1, 'message.delta', { delta: '第一段 ' }))
    await flushPromises()
    expect(document.querySelector('#ai-assistant-drawer')?.textContent).toContain('第一段 ')
    pushEvent?.(event(2, 'message.delta', { delta: '第二段' }))
    await flushPromises()
    expect(document.querySelector('#ai-assistant-drawer')?.textContent).toContain('第一段 第二段')

    const terminal = event(3, 'response.completed')
    pushEvent?.(terminal)
    complete?.(terminal)
    await flushPromises()
    wrapper.unmount()
  })

  it('cancels only the active AI request, returns idle, and permits a text-only retry', async () => {
    let requestSignal: AbortSignal | undefined
    apiMocks.streamAIResponse.mockImplementationOnce((options) => {
      requestSignal = options.signal
      return new Promise((_resolve, reject) => {
        options.signal?.addEventListener('abort', () => reject(options.signal?.reason), { once: true })
      })
    })
    const { wrapper, pinia, router } = await mountDrawer()
    await openDrawer()
    inputMessage('可取消的文字问题')
    await flushPromises()

    document.querySelector<HTMLButtonElement>('button[aria-label="停止 AI 生成"]')?.click()
    await flushPromises()
    const store = useAIAssistantStore(pinia)
    expect(requestSignal?.aborted).toBe(true)
    expect(store.status).toBe('idle')
    expect(store.messages.at(-1)?.status).toBe('cancelled')
    expect(router.currentRoute.value.name).toBe('injection-scheduling-v2')
    expect(document.querySelector('#ai-assistant-drawer')?.textContent).toContain('业务页面未受影响')

    document.querySelector<HTMLButtonElement>('button[aria-label="仅重新发送上一条文字问题"]')?.click()
    await flushPromises()
    expect(apiMocks.streamAIResponse).toHaveBeenCalledTimes(2)
    expect(store.messages.at(-1)?.status).toBe('complete')
    wrapper.unmount()
  })

  it('shows bounded rate-limit recovery details and never auto-retries an image request', async () => {
    const { wrapper, pinia } = await mountDrawer()
    const store = useAIAssistantStore(pinia)
    apiMocks.streamAIResponse.mockRejectedValueOnce(new AIClientError('AI 请求较多，请稍后重试。', {
      code: 'AI_RATE_LIMITED',
      status: 429,
      retryable: true,
      retryAfterSeconds: 15,
    }))

    await store.sendMessage('图片失败不应自动重放', null, [{
      id: 'pilot-image-1',
      media_type: 'image/png',
      data_url: 'data:image/png;base64,AA==',
    }], {
      accepted: true,
      notice_version: 'aliyun-cn-beijing-v1',
      attachment_ids: ['pilot-image-1'],
    })

    expect(store.lastError).toContain('建议 15 秒后再试')
    expect(store.canRetry).toBe(false)
    expect(apiMocks.streamAIResponse).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('invalidates cached capabilities and hides the drawer after a server Pilot denial', async () => {
    apiMocks.streamAIResponse.mockRejectedValueOnce(new AIClientError('当前账号或厂区未加入 AI Pilot，请联系管理员开通。', {
      code: 'AI_PILOT_ACCESS_DENIED',
      status: 403,
      retryable: false,
    }))
    const { wrapper, pinia } = await mountDrawer()
    await openDrawer()
    inputMessage('服务端重新核验准入')
    await flushPromises()

    expect(useAIAssistantStore(pinia).capabilities).toBeNull()
    expect(document.querySelector('#ai-assistant-drawer')).toBeNull()
    expect(triggerButton()).toBeNull()
    wrapper.unmount()
  })

  it('keeps tool results inside the single conversation scroller and the composer outside it', async () => {
    apiMocks.streamAIResponse.mockImplementationOnce(async (options) => {
      options.onEvent(event(1, 'tool.completed', {
        tool_call_id: 'help-layout-1',
        tool_name: 'knowledge.get_module_help',
        status: 'completed',
        result: {
          ok: true,
          tool_name: 'knowledge.get_module_help',
          data: {
            source_type: 'VERSIONED_MODULE_KNOWLEDGE',
            module_name: '注塑排产页面帮助',
            last_reviewed_at: '2026-08-11',
            help_markdown: '帮助内容'.repeat(1_000),
          },
          error: null,
          metadata: {},
        },
      }))
      options.onEvent(event(2, 'response.completed'))
      return event(2, 'response.completed')
    })
    const { wrapper } = await mountDrawer()
    await openDrawer()
    inputMessage('页面帮助')
    await flushPromises()

    const scroller = document.querySelector<HTMLElement>('[role="log"]')
    const results = document.querySelector<HTMLElement>('[data-ai-business-results]')
    const composer = document.querySelector<HTMLElement>('[data-ai-composer]')
    expect(results).not.toBeNull()
    expect(composer).not.toBeNull()
    expect(scroller?.contains(results)).toBe(true)
    expect(scroller?.contains(composer)).toBe(false)
    expect(composer?.className).toContain('shrink-0')
    wrapper.unmount()
  })

  it('marks overlong model output as truncated instead of silently completing it', async () => {
    apiMocks.streamAIResponse.mockImplementationOnce(async (options) => {
      options.onEvent(event(1, 'message.delta', { delta: '长'.repeat(8_001) }))
      options.onEvent(event(2, 'response.completed'))
      return event(2, 'response.completed')
    })
    const { wrapper, pinia } = await mountDrawer()
    await openDrawer()
    inputMessage('生成长回答')
    await flushPromises()

    const assistant = useAIAssistantStore(pinia).messages.at(-1)
    expect(assistant?.text).toHaveLength(8_000)
    expect(assistant?.status).toBe('truncated')
    expect(document.querySelector('#ai-assistant-drawer')?.textContent).toContain('回答过长，后续内容未显示')
    wrapper.unmount()
  })

  it('aborts and clears all in-memory conversation state when the drawer closes', async () => {
    let requestSignal: AbortSignal | undefined
    apiMocks.streamAIResponse.mockImplementationOnce((options) => {
      requestSignal = options.signal
      return new Promise((_resolve, reject) => {
        options.signal?.addEventListener('abort', () => reject(options.signal?.reason), { once: true })
      })
    })
    const { wrapper, pinia } = await mountDrawer()
    await openDrawer()
    inputMessage('保持流式')
    await flushPromises()
    expect(useAIAssistantStore(pinia).messages.length).toBeGreaterThan(0)

    document.querySelector<HTMLButtonElement>('button[aria-label="关闭 AI 助手并清空对话"]')?.click()
    await flushPromises()
    expect(requestSignal?.aborted).toBe(true)
    expect(useAIAssistantStore(pinia).messages).toEqual([])
    expect(useAIAssistantStore(pinia).activities).toEqual([])
    wrapper.unmount()
  })

  it('aborts, clears and hides immediately when sessionVersion changes on logout', async () => {
    let requestSignal: AbortSignal | undefined
    apiMocks.streamAIResponse.mockImplementationOnce((options) => {
      requestSignal = options.signal
      return new Promise((_resolve, reject) => {
        options.signal?.addEventListener('abort', () => reject(options.signal?.reason), { once: true })
      })
    })
    const { wrapper, pinia } = await mountDrawer()
    await openDrawer()
    inputMessage('退出前请求')
    await flushPromises()

    useAuthStore(pinia).clearSession()
    await flushPromises()
    expect(requestSignal?.aborted).toBe(true)
    expect(useAIAssistantStore(pinia).messages).toEqual([])
    expect(triggerButton()).toBeNull()
    wrapper.unmount()
  })

  it('does not use browser persistence for messages or capabilities', () => {
    expect(aiStoreSource).not.toMatch(/localStorage|indexedDB|IndexedDB/)
  })
})
