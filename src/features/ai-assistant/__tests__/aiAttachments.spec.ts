import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  getAICapabilities: vi.fn(),
  streamAIResponse: vi.fn(),
}))
const artifactMocks = vi.hoisted(() => ({
  uploadVisionArtifact: vi.fn(),
}))

vi.mock('@/api/ai', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/api/ai')>(),
  getAICapabilities: apiMocks.getAICapabilities,
  streamAIResponse: apiMocks.streamAIResponse,
}))

vi.mock('@/api/aiArtifacts', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/api/aiArtifacts')>(),
  uploadVisionArtifact: artifactMocks.uploadVisionArtifact,
}))

import type { AuthMeResponse } from '@/api/auth'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import AiAssistantDrawer from '../AiAssistantDrawer.vue'
import AiAttachmentTray from '../AiAttachmentTray.vue'
import type {
  AICapabilities,
  AIArtifactAttachmentReference,
  AIArtifactEgressConsent,
  AICloudProcessingConsent,
  AIRequestAttachment,
  AIStreamEnvelope,
} from '../types'

const visionCapabilities: AICapabilities = {
  enabled: true,
  available: true,
  provider: 'qwen',
  model: 'qwen3.7-plus',
  streaming: true,
  vision_enabled: true,
  conversation_persistence: false,
  adaptive_surface_enabled: true,
  rich_message_renderer_enabled: true,
  presentation_blocks_enabled: true,
  tool_groups: ['module_help'],
  pilot_access: { granted: true, status: 'GRANTED', read_only: true },
}

interface TrayHandle {
  addFiles: (files: readonly File[]) => Promise<void>
  clear: () => void
  prepareForSend: (factoryId?: string) => Promise<{
    attachments: AIRequestAttachment[]
    consent: AICloudProcessingConsent | null
    artifactAttachments: AIArtifactAttachmentReference[]
    artifactConsent: AIArtifactEgressConsent | null
  } | null>
}

const gifSignature = Uint8Array.from([0x47, 0x49, 0x46, 0x38, 0x39, 0x61])
let objectUrlSequence = 0
let createObjectUrl: ReturnType<typeof vi.fn>
let revokeObjectUrl: ReturnType<typeof vi.fn>

function setUint24LittleEndian(bytes: Uint8Array, offset: number, value: number) {
  bytes[offset] = value & 0xff
  bytes[offset + 1] = (value >> 8) & 0xff
  bytes[offset + 2] = (value >> 16) & 0xff
}

function pngBytes(width: number, height: number) {
  const bytes = new Uint8Array(33)
  bytes.set([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a], 0)
  new DataView(bytes.buffer).setUint32(8, 13)
  bytes.set([0x49, 0x48, 0x44, 0x52], 12)
  new DataView(bytes.buffer).setUint32(16, width)
  new DataView(bytes.buffer).setUint32(20, height)
  bytes.set([8, 2, 0, 0, 0], 24)
  return bytes
}

function imageFile(name = 'screen.png', width = 32, height = 32) {
  return new File([pngBytes(width, height)], name, { type: 'image/png' })
}

function jpegFile(name = 'screen.jpg', width = 32, height = 32) {
  const bytes = Uint8Array.from([
    0xff, 0xd8,
    0xff, 0xc0, 0x00, 0x0b, 0x08,
    (height >> 8) & 0xff, height & 0xff,
    (width >> 8) & 0xff, width & 0xff,
    0x01, 0x01, 0x11, 0x00,
    0xff, 0xd9,
  ])
  return new File([bytes], name, { type: 'image/jpeg' })
}

function webpFile(name = 'screen.webp', width = 32, height = 32, animated = false) {
  const bytes = new Uint8Array(48)
  bytes.set([0x52, 0x49, 0x46, 0x46], 0)
  new DataView(bytes.buffer).setUint32(4, 40, true)
  bytes.set([0x57, 0x45, 0x42, 0x50, 0x56, 0x50, 0x38, 0x58], 8)
  new DataView(bytes.buffer).setUint32(16, 10, true)
  bytes[20] = animated ? 0x02 : 0
  setUint24LittleEndian(bytes, 24, width - 1)
  setUint24LittleEndian(bytes, 27, height - 1)
  bytes.set([0x56, 0x50, 0x38, 0x20], 30)
  new DataView(bytes.buffer).setUint32(34, 10, true)
  bytes.set([0, 0, 0, 0x9d, 0x01, 0x2a], 38)
  new DataView(bytes.buffer).setUint16(44, width, true)
  new DataView(bytes.buffer).setUint16(46, height, true)
  return new File([bytes], name, { type: 'image/webp' })
}

function event(
  sequence: number,
  type: string,
  payload: Record<string, unknown> = {},
): AIStreamEnvelope {
  return {
    schema_version: '1',
    request_id: 'web-attachment-test',
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
      {
        path: '/',
        name: 'dashboard',
        component: { template: '<div />' },
        meta: { requiresAuth: true },
      },
      {
        path: '/modules/sales/internal-quotes',
        name: 'internal-quotes',
        component: { template: '<div />' },
        meta: { requiresAuth: true },
      },
      {
        path: '/modules/production/injection-scheduling',
        name: 'injection-scheduling-v2',
        component: { template: '<div />' },
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
  capabilities = visionCapabilities,
  path = '/modules/production/injection-scheduling?factory=huaxing',
) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = createTestRouter()
  await router.push(path)
  await router.isReady()
  const auth = authenticate(pinia)
  useAppStore(pinia).activeFactoryId = 'huaxing'
  apiMocks.getAICapabilities.mockResolvedValue(capabilities)
  const wrapper = mount(AiAssistantDrawer, {
    attachTo: document.body,
    global: { plugins: [pinia, router] },
  })
  await flushPromises()
  document.querySelector<HTMLButtonElement>('#ai-assistant-trigger')?.click()
  await flushPromises()
  return { wrapper, pinia, auth, router }
}

function transferEvent(type: 'paste' | 'drop', files: File[]) {
  const transfer = { files, types: ['Files'] }
  const transferEvent = new Event(type, { bubbles: true, cancelable: true })
  Object.defineProperty(transferEvent, type === 'drop' ? 'dataTransfer' : 'clipboardData', {
    configurable: true,
    value: transfer,
  })
  return transferEvent
}

function inputMessage(value: string) {
  const textarea = document.querySelector<HTMLTextAreaElement>('#ai-assistant-message')
  if (!textarea) throw new Error('composer missing')
  textarea.value = value
  textarea.dispatchEvent(new Event('input', { bubbles: true }))
  textarea.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
}

beforeEach(() => {
  objectUrlSequence = 0
  createObjectUrl = vi.fn(() => `blob:ai-preview-${++objectUrlSequence}`)
  revokeObjectUrl = vi.fn()
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectUrl })
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectUrl })
  apiMocks.getAICapabilities.mockReset()
  apiMocks.streamAIResponse.mockReset()
  artifactMocks.uploadVisionArtifact.mockReset()
  apiMocks.streamAIResponse.mockImplementation(async (options) => {
    const hasAttachments = Boolean(options.attachments?.length)
    options.onEvent(event(1, 'response.started', {
      attachment_count: options.attachments?.length ?? 0,
      ...(hasAttachments ? { input_source: 'USER_PROVIDED' } : {}),
    }))
    options.onEvent(event(2, 'message.delta', {
      delta: hasAttachments ? '图片识别结果' : '纯文本帮助',
      ...(hasAttachments ? { source: 'MODEL_INFERENCE' } : {}),
    }))
    if (hasAttachments) options.onEvent(event(3, 'warning', { source: 'FORMAL' }))
    const terminal = event(hasAttachments ? 4 : 3, 'response.completed')
    options.onEvent(terminal)
    return terminal
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

describe('AI image attachment safety', () => {
  it('parses PNG, JPEG and WebP dimensions before creating previews', async () => {
    const wrapper = mount(AiAttachmentTray)
    const tray = wrapper.vm as unknown as TrayHandle
    await tray.addFiles([imageFile(), jpegFile(), webpFile()])
    expect(wrapper.findAll('img')).toHaveLength(3)
    expect(createObjectUrl).toHaveBeenCalledTimes(3)
    wrapper.unmount()
  })

  it('rejects per-image and aggregate pixel bombs before browser image decode', async () => {
    const wrapper = mount(AiAttachmentTray)
    const tray = wrapper.vm as unknown as TrayHandle

    await tray.addFiles([imageFile('pixel-bomb.png', 5_000, 4_000)])
    expect(wrapper.text()).toContain('单张图片不能超过 1600 万像素')
    expect(wrapper.findAll('img')).toHaveLength(0)
    expect(createObjectUrl).not.toHaveBeenCalled()

    await tray.addFiles([webpFile('animated.webp', 32, 32, true)])
    expect(wrapper.text()).toContain('不支持动画 WebP')
    expect(createObjectUrl).not.toHaveBeenCalled()

    await tray.addFiles([imageFile('twelve-megapixels.png', 4_000, 3_000)])
    expect(wrapper.findAll('img')).toHaveLength(1)
    await tray.addFiles([imageFile('thirteen-megapixels.png', 4_000, 3_250)])
    expect(wrapper.text()).toContain('每次图片合计不能超过 2400 万像素')
    expect(wrapper.findAll('img')).toHaveLength(1)
    expect(createObjectUrl).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('supports the hidden file selection control', async () => {
    const wrapper = mount(AiAttachmentTray)
    const input = wrapper.find<HTMLInputElement>('input[type="file"]')
    Object.defineProperty(input.element, 'files', {
      configurable: true,
      value: [imageFile('selected.png')],
    })
    await input.trigger('change')
    await vi.waitFor(() => expect(wrapper.findAll('img')).toHaveLength(1))
    expect(input.element.value).toBe('')
    wrapper.unmount()
  })

  it('rejects false MIME content, empty, oversized and excess files before request preparation', async () => {
    const wrapper = mount(AiAttachmentTray)
    const tray = wrapper.vm as unknown as TrayHandle

    await tray.addFiles([new File([gifSignature], 'fake.png', { type: 'image/png' })])
    expect(wrapper.text()).toContain('图片类型与文件内容不一致')
    expect(wrapper.findAll('img')).toHaveLength(0)

    await tray.addFiles([new File([], 'empty.png', { type: 'image/png' })])
    expect(wrapper.text()).toContain('不能添加空图片')

    await tray.addFiles([new File([new Uint8Array(4 * 1024 * 1024 + 1)], 'large.png', { type: 'image/png' })])
    expect(wrapper.text()).toContain('单张图片不能超过 4 MiB')

    await tray.addFiles([imageFile('1.png'), imageFile('2.png'), imageFile('3.png')])
    expect(wrapper.findAll('img')).toHaveLength(3)
    await tray.addFiles([imageFile('4.png')])
    expect(wrapper.text()).toContain('每次最多添加 3 张图片')
    tray.clear()
    await Promise.all([
      tray.addFiles([imageFile('parallel-1.png'), imageFile('parallel-2.png')]),
      tray.addFiles([imageFile('parallel-3.png'), imageFile('parallel-4.png')]),
    ])
    expect(wrapper.findAll('img')).toHaveLength(2)
    expect(wrapper.text()).toContain('每次最多添加 3 张图片')
    wrapper.unmount()
  })

  it('requires fresh explicit consent and prepares only the minimal contract', async () => {
    const wrapper = mount(AiAttachmentTray)
    const tray = wrapper.vm as unknown as TrayHandle
    await tray.addFiles([imageFile()])

    expect(wrapper.text()).toContain('本次图片将发送至阿里云百炼华北2（北京）')
    expect(wrapper.text()).toContain('由qwen3.7-plus处理')
    expect(wrapper.text()).toContain('store=false不代表供应商零留存')
    expect(wrapper.text()).toContain('调用数据可能依法存储')
    await expect(tray.prepareForSend()).resolves.toBeNull()
    expect(wrapper.text()).toContain('请先确认')

    await wrapper.find('input[type="checkbox"]').setValue(true)
    const prepared = await tray.prepareForSend()
    expect(prepared?.attachments).toHaveLength(1)
    expect(prepared?.attachments[0]).toMatchObject({ media_type: 'image/png' })
    expect(prepared?.attachments[0]?.data_url).toMatch(/^data:image\/png;base64,/)
    expect(prepared?.attachments[0]).not.toHaveProperty('source_type')
    expect(prepared?.consent).toEqual({
      accepted: true,
      notice_version: 'aliyun-cn-beijing-v1',
      attachment_ids: [prepared?.attachments[0]?.id],
    })

    await tray.addFiles([imageFile('second.png')])
    expect((wrapper.find('input[type="checkbox"]').element as HTMLInputElement).checked).toBe(false)
    tray.clear()
    await wrapper.vm.$nextTick()
    expect(revokeObjectUrl).toHaveBeenCalledTimes(2)
    expect(wrapper.find('input[type="checkbox"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('uploads each approved image once and prepares only Artifact references', async () => {
    const artifactId = `aiart-${'a'.repeat(32)}`
    artifactMocks.uploadVisionArtifact.mockResolvedValue({
      id: artifactId,
      factory_id: 'huaxing',
      original_filename: 'screen.png',
      normalized_extension: '.png',
      detected_mime_type: 'image/png',
      content_class: 'IMAGE',
      size_bytes: 33,
      sha256: 'b'.repeat(64),
      classification: 'CONFIDENTIAL_BUSINESS',
      status: 'ACTIVE',
      scanner_status: 'CLEAN',
      parser_status: 'NOT_REQUESTED',
      parent_artifact_id: null,
      derivation_type: 'ORIGINAL',
      parser_version: '',
      model_version: '',
      retention_until: '2026-09-11T00:00:00+08:00',
      created_at: '2026-08-12T00:00:00+08:00',
      updated_at: '2026-08-12T00:00:00+08:00',
    })
    const wrapper = mount(AiAttachmentTray, {
      props: { artifactWorkflowEnabled: true },
    })
    const tray = wrapper.vm as unknown as TrayHandle
    await tray.addFiles([imageFile()])
    await wrapper.find('input[type="checkbox"]').setValue(true)

    const prepared = await tray.prepareForSend('huaxing')

    expect(artifactMocks.uploadVisionArtifact).toHaveBeenCalledOnce()
    expect(artifactMocks.uploadVisionArtifact).toHaveBeenCalledWith(
      expect.any(File),
      'huaxing',
      'CONFIDENTIAL_BUSINESS',
    )
    expect(prepared).toMatchObject({
      attachments: [],
      consent: null,
      artifactAttachments: [{ artifact_id: artifactId }],
      artifactConsent: {
        accepted: true,
        notice_version: 'aliyun-cn-beijing-image-v1',
        provider: 'qwen',
        region: 'cn-beijing',
        classification: 'CONFIDENTIAL_BUSINESS',
        content_class: 'IMAGE',
        artifact_ids: [artifactId],
      },
    })
    expect(JSON.stringify(prepared)).not.toContain('data:image/')
    wrapper.unmount()
  })

  it('aborts the active reader immediately when the user withdraws consent', async () => {
    const readers: ControlledFileReader[] = []
    const abortReader = vi.fn()
    class ControlledFileReader {
      static readonly LOADING = 1
      readyState = 0
      result: string | ArrayBuffer | null = null
      onload: (() => void) | null = null
      onerror: (() => void) | null = null
      onabort: (() => void) | null = null

      readAsDataURL() {
        this.readyState = ControlledFileReader.LOADING
        readers.push(this)
      }

      abort() {
        abortReader()
        this.readyState = 2
        this.onabort?.()
      }
    }
    vi.stubGlobal('FileReader', ControlledFileReader)
    const wrapper = mount(AiAttachmentTray)
    const tray = wrapper.vm as unknown as TrayHandle
    await tray.addFiles([imageFile('reader-1.png'), imageFile('reader-2.png')])
    await wrapper.find('input[type="checkbox"]').setValue(true)

    const pending = tray.prepareForSend()
    await vi.waitFor(() => expect(readers).toHaveLength(1))
    const consent = wrapper.find<HTMLInputElement>('input[type="checkbox"]')
    await consent.setValue(false)

    await expect(pending).resolves.toBeNull()
    expect(abortReader).toHaveBeenCalledTimes(1)
    expect(readers).toHaveLength(1)
    expect(wrapper.text()).toContain('页面、厂区或图片已变化')
    wrapper.unmount()
  })

  it('accepts paste and drop, blocks send without consent, then clears previews after completion', async () => {
    const { wrapper } = await mountDrawer()
    const textarea = document.querySelector<HTMLTextAreaElement>('#ai-assistant-message')
    const drawer = document.querySelector<HTMLElement>('#ai-assistant-drawer')
    textarea?.dispatchEvent(transferEvent('paste', [imageFile('paste.png')]))
    drawer?.dispatchEvent(transferEvent('drop', [imageFile('drop.png')]))
    await vi.waitFor(() => expect(document.querySelectorAll('[data-ai-attachment-tray] img')).toHaveLength(2))

    inputMessage('识别截图')
    await flushPromises()
    expect(apiMocks.streamAIResponse).not.toHaveBeenCalled()
    expect(document.querySelector<HTMLTextAreaElement>('#ai-assistant-message')?.value).toBe('识别截图')
    expect(document.querySelector('[data-ai-attachment-tray] [role="alert"]')?.textContent).toContain('请先确认')

    const checkbox = document.querySelector<HTMLInputElement>('[data-ai-attachment-tray] input[type="checkbox"]')
    checkbox?.click()
    inputMessage('识别截图')
    await vi.waitFor(() => expect(apiMocks.streamAIResponse).toHaveBeenCalledTimes(1))
    const options = apiMocks.streamAIResponse.mock.calls[0]?.[0]
    expect(options.attachments).toHaveLength(2)
    expect(options.cloudProcessingConsent).toEqual({
      accepted: true,
      notice_version: 'aliyun-cn-beijing-v1',
      attachment_ids: options.attachments.map((item: AIRequestAttachment) => item.id),
    })
    expect(options.messages.at(-1)).toEqual({
      role: 'user',
      content: [{ type: 'input_text', text: '识别截图' }],
    })
    expect(document.querySelector('#ai-assistant-drawer')?.textContent).toContain('用户提供内容')
    expect(document.querySelector('#ai-assistant-drawer')?.textContent).toContain('模型推断')
    expect(document.querySelector('#ai-assistant-drawer')?.textContent).not.toContain('系统正式数据')
    await vi.waitFor(() => expect(document.querySelectorAll('[data-ai-attachment-tray] img')).toHaveLength(0))
    expect(revokeObjectUrl).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('hides every attachment entry when Vision is off while text streaming still works', async () => {
    const { wrapper } = await mountDrawer({ ...visionCapabilities, vision_enabled: false })
    expect(document.querySelector('[data-ai-attachment-tray]')).toBeNull()
    expect(document.querySelector('input[type="file"]')).toBeNull()
    expect(document.querySelector('#ai-assistant-drawer')?.textContent).toContain('当前仅支持文字')

    inputMessage('文字帮助')
    await vi.waitFor(() => expect(apiMocks.streamAIResponse).toHaveBeenCalledTimes(1))
    expect(apiMocks.streamAIResponse.mock.calls[0]?.[0].attachments).toEqual([])
    expect(apiMocks.streamAIResponse.mock.calls[0]?.[0].cloudProcessingConsent).toBeNull()
    wrapper.unmount()
  })

  it('keeps text available but hides attachments outside a verified module context', async () => {
    const { wrapper, router } = await mountDrawer(visionCapabilities, '/')
    expect(document.querySelector('#ai-assistant-drawer')).not.toBeNull()
    expect(document.querySelector('[data-ai-attachment-tray]')).toBeNull()
    expect(document.querySelector('input[type="file"]')).toBeNull()

    inputMessage('主页文字帮助')
    await vi.waitFor(() => expect(apiMocks.streamAIResponse).toHaveBeenCalledTimes(1))
    expect(apiMocks.streamAIResponse.mock.calls[0]?.[0].attachments).toEqual([])
    expect(apiMocks.streamAIResponse.mock.calls[0]?.[0].pageContext).toBeNull()

    await router.push('/modules/sales/internal-quotes')
    await flushPromises()
    expect(document.querySelector('[data-ai-attachment-tray]')).toBeNull()
    expect(document.querySelector('#ai-assistant-drawer')).not.toBeNull()
    wrapper.unmount()
  })

  it('clears images and consent when factory_id becomes null while keeping text available', async () => {
    const { wrapper, router } = await mountDrawer()
    document.querySelector<HTMLElement>('#ai-assistant-drawer')?.dispatchEvent(
      transferEvent('drop', [imageFile('null-factory.png')]),
    )
    await vi.waitFor(() => expect(document.querySelectorAll('[data-ai-attachment-tray] img')).toHaveLength(1))
    const consent = document.querySelector<HTMLInputElement>(
      '[data-ai-attachment-tray] input[type="checkbox"]',
    )
    consent?.click()

    await router.push('/modules/production/injection-scheduling?factory=forged')
    await flushPromises()
    expect(document.querySelector('[data-ai-attachment-tray]')).toBeNull()
    expect(revokeObjectUrl).toHaveBeenCalledTimes(1)

    inputMessage('空厂区仍可使用文字帮助')
    await vi.waitFor(() => expect(apiMocks.streamAIResponse).toHaveBeenCalledTimes(1))
    expect(apiMocks.streamAIResponse.mock.calls[0]?.[0].attachments).toEqual([])
    expect(apiMocks.streamAIResponse.mock.calls[0]?.[0].pageContext).toMatchObject({
      route_name: 'injection-scheduling-v2',
      module_id: 'injection-scheduling',
      factory_id: null,
    })
    wrapper.unmount()
  })

  it('clears attachment memory immediately when leaving the verified scheduling page', async () => {
    const { wrapper, router } = await mountDrawer()
    document.querySelector<HTMLElement>('#ai-assistant-drawer')?.dispatchEvent(
      transferEvent('drop', [imageFile('leave-page.png')]),
    )
    await vi.waitFor(() => expect(document.querySelectorAll('[data-ai-attachment-tray] img')).toHaveLength(1))

    await router.push('/')
    await flushPromises()
    expect(document.querySelector('[data-ai-attachment-tray]')).toBeNull()
    expect(revokeObjectUrl).toHaveBeenCalledTimes(1)
    expect(document.querySelector('#ai-assistant-drawer')).not.toBeNull()
    inputMessage('切换后的文字帮助')
    await vi.waitFor(() => expect(apiMocks.streamAIResponse).toHaveBeenCalledTimes(1))
    expect(apiMocks.streamAIResponse.mock.calls[0]?.[0].attachments).toEqual([])
    wrapper.unmount()
  })

  it('revokes in-memory previews on close and logout', async () => {
    const { wrapper, auth } = await mountDrawer()
    const drawer = document.querySelector<HTMLElement>('#ai-assistant-drawer')
    drawer?.dispatchEvent(transferEvent('drop', [imageFile('close.png')]))
    await vi.waitFor(() => expect(document.querySelectorAll('[data-ai-attachment-tray] img')).toHaveLength(1))
    document.querySelector<HTMLButtonElement>('button[aria-label="关闭 AI 助手并清空对话"]')?.click()
    await flushPromises()
    expect(revokeObjectUrl).toHaveBeenCalledTimes(1)

    document.querySelector<HTMLButtonElement>('#ai-assistant-trigger')?.click()
    await flushPromises()
    document.querySelector<HTMLElement>('#ai-assistant-drawer')?.dispatchEvent(transferEvent('drop', [imageFile('logout.png')]))
    await vi.waitFor(() => expect(document.querySelectorAll('[data-ai-attachment-tray] img')).toHaveLength(1))
    auth.clearSession()
    await flushPromises()
    expect(revokeObjectUrl).toHaveBeenCalledTimes(2)
    expect(document.querySelector('#ai-assistant-trigger')).toBeNull()
    wrapper.unmount()
  })

  it('resets current-batch consent when route or factory context changes', async () => {
    const { wrapper, pinia, router } = await mountDrawer()
    document.querySelector<HTMLElement>('#ai-assistant-drawer')?.dispatchEvent(
      transferEvent('drop', [imageFile('context.png')]),
    )
    await vi.waitFor(() => expect(document.querySelectorAll('[data-ai-attachment-tray] img')).toHaveLength(1))
    const consent = () => document.querySelector<HTMLInputElement>(
      '[data-ai-attachment-tray] input[type="checkbox"]',
    )
    const firstConsent = consent()
    if (!firstConsent) throw new Error('consent checkbox missing')
    firstConsent.checked = true
    firstConsent.dispatchEvent(new Event('change', { bubbles: true }))
    await flushPromises()
    expect(consent()?.checked).toBe(true)

    await router.push('/modules/production/injection-scheduling?factory=huakang-b')
    await flushPromises()
    expect(consent()?.checked).toBe(false)

    const secondConsent = consent()
    if (!secondConsent) throw new Error('consent checkbox missing')
    secondConsent.checked = true
    secondConsent.dispatchEvent(new Event('change', { bubbles: true }))
    await flushPromises()
    expect(consent()?.checked).toBe(true)
    const appStore = useAppStore(pinia)
    appStore.setActiveFactory(appStore.activeFactoryId === 'huakang-b' ? 'huaxing' : 'huakang-b')
    await flushPromises()
    expect(consent()?.checked).toBe(false)
    wrapper.unmount()
  })
})
