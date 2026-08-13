import { http, dispatchAccessFailure } from '@/lib/http'
import type {
  AICapabilities,
  AIChatRequestMessage,
  AIArtifactAttachmentReference,
  AIArtifactEgressConsent,
  AICloudProcessingConsent,
  AIFailure,
  AIPageContext,
  AIPilotAccessStatus,
  AIRequestAttachment,
  AIStreamEnvelope,
} from '@/features/ai-assistant/types'

const REQUEST_ID_PATTERN = /^[A-Za-z0-9._-]{1,128}$/
const DEFAULT_STREAM_TIMEOUT_MS = 70_000
const MAX_SSE_LINE_CHARS = 512 * 1024
const MAX_SSE_FRAME_CHARS = 1024 * 1024
const MAX_SSE_RESPONSE_BYTES = 8 * 1024 * 1024
const MAX_SSE_EVENTS = 4_096

interface AIErrorPayload {
  code?: unknown
  message?: unknown
  retryable?: unknown
  retry_after_seconds?: unknown
}

const AI_ERROR_CODE_PATTERN = /^AI_[A-Z0-9_]{1,76}$/
const MAX_RETRY_AFTER_SECONDS = 3_600
const AI_PUBLIC_ERROR_MESSAGES: Readonly<Record<string, string>> = Object.freeze({
  AI_PILOT_ACCESS_DENIED: '当前账号或厂区未加入 AI Pilot，请联系管理员开通。',
  AI_CONCURRENT_REQUEST_LIMIT: '你已有一个 AI 请求正在处理，请等待完成或先停止。',
  AI_RATE_LIMITED: 'AI 请求较多，请稍后重试。',
  AI_BUDGET_EXCEEDED: '当前 AI 预算额度已用完，请稍后再试或联系管理员。',
  AI_DISABLED: 'AI Pilot 当前已关闭，请联系管理员。',
  AI_NOT_CONFIGURED: 'AI 服务尚未完成配置，请联系管理员。',
  AI_PROVIDER_AUTHENTICATION_FAILED: 'AI 服务配置异常，请联系管理员。',
  AI_PROVIDER_UNAVAILABLE: '云端 AI 服务暂时不可用，请稍后重试。',
  AI_REQUEST_FAILED: 'AI 服务暂时不可用，请稍后重试。',
  AI_INTERNAL_ERROR: 'AI 服务暂时不可用，请稍后重试。',
  AI_TIMEOUT: 'AI 响应超时，请缩小问题范围后重试。',
  AI_CLIENT_TIMEOUT: 'AI 响应超时，请缩小问题范围后重试。',
  AI_TOOL_TIMEOUT: '读取业务信息超时，请缩小问题范围后重试。',
  AI_TOOL_ROUND_LIMIT: '本次问题需要的步骤过多，请缩小范围后重试。',
  AI_PROVIDER_PROTOCOL_ERROR: 'AI 连接意外中断，请重新发起请求。',
  AI_STREAM_INTERRUPTED: 'AI 连接意外中断，请重新发起请求。',
  AI_INVALID_SSE_JSON: 'AI 连接意外中断，请重新发起请求。',
  AI_INVALID_SSE_EVENT: 'AI 连接意外中断，请重新发起请求。',
  AI_INVALID_SSE_SEQUENCE: 'AI 连接意外中断，请重新发起请求。',
  AI_SSE_LINE_TOO_LARGE: 'AI 响应超过安全限制，请缩小问题范围后重试。',
  AI_SSE_FRAME_TOO_LARGE: 'AI 响应超过安全限制，请缩小问题范围后重试。',
  AI_SSE_RESPONSE_TOO_LARGE: 'AI 响应超过安全限制，请缩小问题范围后重试。',
  AI_SSE_EVENT_LIMIT: 'AI 响应超过安全限制，请缩小问题范围后重试。',
  AI_INVALID_PAGE_CONTEXT: '当前页面上下文不支持此 AI 请求，请刷新页面后重试。',
  AI_TOOL_PERMISSION_DENIED: '当前账号无权读取所请求的业务信息。',
  AI_TOOL_DEPARTMENT_NOT_ALLOWED: '当前账号无权读取所请求的业务信息。',
  AI_TOOL_INVALID_FACTORY: '当前厂区不允许读取所请求的业务信息。',
  AI_TOOL_RISK_NOT_ALLOWED: '该请求超出 AI Pilot 的只读范围。',
  AI_TOOL_UNKNOWN: '该请求不在 AI Pilot 的已开放能力范围内。',
  AI_UNEXPECTED_TOOL_CALL: '该请求不在 AI Pilot 的已开放能力范围内。',
  AI_ATTACHMENT_ANIMATED_IMAGE: '暂不支持动态图片，请改用静态 PNG、JPEG 或 WebP。',
  AI_ATTACHMENT_EMPTY: '图片内容为空，请重新选择。',
  AI_ATTACHMENT_INVALID_DATA_URL: '图片格式无效，请重新选择。',
  AI_ATTACHMENT_INVALID_IMAGE: '图片未通过安全校验，请重新选择。',
  AI_ATTACHMENT_MEDIA_TYPE_MISMATCH: '图片类型与内容不一致，请重新选择。',
  AI_ATTACHMENT_PIXEL_LIMIT: '图片像素过大，请压缩后重新选择。',
  AI_ATTACHMENT_TOO_LARGE: '图片文件过大，请压缩后重新选择。',
  AI_ATTACHMENT_TOO_MANY: '每次最多发送 3 张图片。',
})

export class AIClientError extends Error {
  readonly code: string
  readonly status?: number
  readonly retryable: boolean
  readonly retryAfterSeconds?: number
  readonly requestId?: string

  constructor(
    message: string,
    options: {
      code: string
      status?: number
      retryable?: boolean
      retryAfterSeconds?: number
      requestId?: string
    },
  ) {
    super(message)
    this.name = 'AIClientError'
    this.code = options.code
    this.status = options.status
    this.retryable = options.retryable ?? false
    this.retryAfterSeconds = options.retryAfterSeconds
    this.requestId = options.requestId
  }
}

export interface AIStreamOptions {
  messages: AIChatRequestMessage[]
  conversationId?: string
  pageContext: AIPageContext | null
  attachments?: readonly AIRequestAttachment[]
  cloudProcessingConsent?: AICloudProcessingConsent | null
  artifactAttachments?: readonly AIArtifactAttachmentReference[]
  artifactEgressConsent?: AIArtifactEgressConsent | null
  signal?: AbortSignal
  timeoutMs?: number
  requestId?: string
  onEvent: (event: AIStreamEnvelope) => void
}

function clearRequestAttachmentData(attachments: readonly AIRequestAttachment[]) {
  attachments.forEach((attachment) => {
    attachment.data_url = ''
  })
}

function apiBaseUrl() {
  const configured = String(import.meta.env?.VITE_API_BASE_URL ?? '/api').trim() || '/api'
  return configured.replace(/\/+$/, '')
}

function createRequestId() {
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return `web-${globalThis.crypto.randomUUID()}`
  }
  if (typeof globalThis.crypto?.getRandomValues !== 'function') {
    throw new AIClientError('当前浏览器无法生成安全请求标识。', {
      code: 'AI_SECURE_RANDOM_UNAVAILABLE',
    })
  }
  const bytes = new Uint8Array(16)
  globalThis.crypto.getRandomValues(bytes)
  const token = Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('')
  return `web-${token}`
}

function normalizePilotStatus(value: unknown): AIPilotAccessStatus {
  const status = typeof value === 'string' ? value.trim().toUpperCase() : ''
  return ['DISABLED', 'TLS_REQUIRED', 'CONTROL_REQUIRED', 'PROVIDER_REQUIRED', 'GRANTED'].includes(status)
    ? status as AIPilotAccessStatus
    : 'UNKNOWN'
}

function normalizeCapabilities(value: unknown): AICapabilities {
  const source = value && typeof value === 'object' ? value as Record<string, unknown> : {}
  const pilotAccess = source.pilot_access && typeof source.pilot_access === 'object'
    && !Array.isArray(source.pilot_access)
    ? source.pilot_access as Record<string, unknown>
    : {}
  return {
    enabled: source.enabled === true,
    available: source.available === true,
    provider: typeof source.provider === 'string' ? source.provider : '',
    model: typeof source.model === 'string' ? source.model : '',
    streaming: source.streaming === true,
    vision_enabled: source.vision_enabled === true,
    conversation_persistence: source.conversation_persistence === true,
    artifact_workflows_enabled: source.artifact_workflows_enabled === true,
    vision_tool_comparison_enabled: source.vision_tool_comparison_enabled === true,
    feedback_enabled: source.feedback_enabled === true,
    tool_groups: Array.isArray(source.tool_groups)
      ? source.tool_groups.filter((item): item is string => typeof item === 'string')
      : [],
    pilot_access: {
      granted: pilotAccess.granted === true,
      status: normalizePilotStatus(pilotAccess.status),
      read_only: pilotAccess.read_only === true,
      max_tool_risk_level: pilotAccess.max_tool_risk_level === 'PREVIEW_WITH_AUDIT'
        ? 'PREVIEW_WITH_AUDIT'
        : 'READ_ONLY',
    },
  }
}

export async function getAICapabilities() {
  const response = await http.get('/ai/capabilities', {
    // Pilot denial is the expected fail-closed result for this endpoint. It
    // must not refresh the auth snapshot and recursively probe capabilities.
    skipForbiddenSessionRefresh: true,
  })
  return normalizeCapabilities(response.data)
}

function publicErrorFrom(value: unknown): AIErrorPayload {
  if (!value || typeof value !== 'object') return {}
  const source = value as Record<string, unknown>
  const detail = source.detail
  if (detail && typeof detail === 'object') return detail as AIErrorPayload
  return source
}

function fallbackErrorMessage(status?: number) {
  if (status === 401) return '登录状态已失效，请重新登录。'
  if (status === 403) return '当前账号无权使用此 AI 能力。'
  if (status === 429) return 'AI 请求较多，请稍后重试。'
  if (status !== undefined && status >= 400 && status < 500) {
    return 'AI 请求未通过校验，请检查内容后重试。'
  }
  return 'AI 服务暂时不可用，请稍后重试。'
}

export function normalizeAIFailure(value: unknown, status?: number): AIFailure {
  const error = publicErrorFrom(value)
  const rawCode = typeof error.code === 'string' ? error.code.trim().toUpperCase() : ''
  const code = AI_ERROR_CODE_PATTERN.test(rawCode)
    ? rawCode
    : status !== undefined
      ? `AI_HTTP_${status}`
      : 'AI_REQUEST_FAILED'
  const retryAfter = typeof error.retry_after_seconds === 'number'
    && Number.isInteger(error.retry_after_seconds)
    && error.retry_after_seconds > 0
    && error.retry_after_seconds <= MAX_RETRY_AFTER_SECONDS
    ? error.retry_after_seconds
    : undefined
  return {
    code,
    message: AI_PUBLIC_ERROR_MESSAGES[code] ?? fallbackErrorMessage(status),
    retryable: error.retryable === true,
    ...(retryAfter !== undefined ? { retryAfterSeconds: retryAfter } : {}),
  }
}

async function readErrorResponse(response: Response, requestId: string) {
  let payload: unknown
  try {
    payload = await response.clone().json()
  } catch {
    payload = undefined
  }
  dispatchAccessFailure(response.status, response.url || `${apiBaseUrl()}/ai/responses`, payload)
  const failure = normalizeAIFailure(payload, response.status)
  throw new AIClientError(failure.message, {
    code: failure.code,
    status: response.status,
    retryable: failure.retryable,
    retryAfterSeconds: failure.retryAfterSeconds,
    requestId,
  })
}

function parseEnvelope(rawData: string, eventName: string, requestId: string): AIStreamEnvelope {
  let value: unknown
  try {
    value = JSON.parse(rawData)
  } catch {
    throw new AIClientError('AI 流式响应格式无效，请重新发起请求。', {
      code: 'AI_INVALID_SSE_JSON',
      requestId,
      retryable: true,
    })
  }
  if (!value || typeof value !== 'object') {
    throw new AIClientError('AI 流式响应格式无效，请重新发起请求。', {
      code: 'AI_INVALID_SSE_EVENT',
      requestId,
      retryable: true,
    })
  }
  const source = value as Record<string, unknown>
  const type = typeof source.type === 'string' ? source.type : ''
  const sequence = typeof source.sequence === 'number' ? source.sequence : Number.NaN
  if (
    source.schema_version !== '1'
    || source.request_id !== requestId
    || !Number.isInteger(sequence)
    || sequence < 1
    || !type
    || (eventName && eventName !== type)
    || typeof source.timestamp !== 'string'
  ) {
    throw new AIClientError('AI 流式响应校验失败，请重新发起请求。', {
      code: 'AI_INVALID_SSE_EVENT',
      requestId,
      retryable: true,
    })
  }
  return {
    schema_version: '1',
    request_id: requestId,
    sequence,
    type,
    timestamp: source.timestamp,
    payload: source.payload && typeof source.payload === 'object' && !Array.isArray(source.payload)
      ? source.payload as Record<string, unknown>
      : {},
  }
}

class SSEFrameParser {
  private lineParts: string[] = []
  private lineLength = 0
  private skipLeadingLf = false
  private eventName = ''
  private dataLines: string[] = []
  private frameCharacters = 0
  private stopped = false

  constructor(
    private readonly requestId: string,
    private readonly onFrame: (eventName: string, data: string) => boolean,
  ) {}

  get isStopped() {
    return this.stopped
  }

  feed(chunk: string) {
    if (this.stopped || !chunk) return
    let segmentStart = 0
    for (let index = 0; index < chunk.length; index += 1) {
      const character = chunk[index]
      if (this.skipLeadingLf) {
        this.skipLeadingLf = false
        if (character === '\n') {
          segmentStart = index + 1
          continue
        }
      }
      if (character !== '\r' && character !== '\n') continue
      this.appendLinePart(chunk.slice(segmentStart, index))
      const line = this.consumeLine()
      this.processLine(line)
      segmentStart = index + 1
      this.skipLeadingLf = character === '\r'
      if (this.stopped) return
    }
    this.appendLinePart(chunk.slice(segmentStart))
  }

  finish() {
    if (this.stopped) return
    if (this.lineLength) this.processLine(this.consumeLine())
    this.dispatch()
  }

  private appendLinePart(part: string) {
    if (!part) return
    this.lineLength += part.length
    if (this.lineLength > MAX_SSE_LINE_CHARS) {
      throw new AIClientError('AI 流式响应单行过长，已停止读取。', {
        code: 'AI_SSE_LINE_TOO_LARGE',
        requestId: this.requestId,
        retryable: true,
      })
    }
    this.lineParts.push(part)
  }

  private consumeLine() {
    const line = this.lineParts.join('')
    this.lineParts = []
    this.lineLength = 0
    return line
  }

  private processLine(line: string) {
    if (!line) {
      this.dispatch()
      return
    }
    this.frameCharacters += line.length
    if (this.frameCharacters > MAX_SSE_FRAME_CHARS) {
      throw new AIClientError('AI 流式响应单帧过长，已停止读取。', {
        code: 'AI_SSE_FRAME_TOO_LARGE',
        requestId: this.requestId,
        retryable: true,
      })
    }
    if (line.startsWith(':')) return
    const separator = line.indexOf(':')
    const field = separator < 0 ? line : line.slice(0, separator)
    let value = separator < 0 ? '' : line.slice(separator + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') this.eventName = value
    if (field === 'data') this.dataLines.push(value)
  }

  private dispatch() {
    this.frameCharacters = 0
    if (!this.dataLines.length) {
      this.eventName = ''
      return
    }
    const data = this.dataLines.join('\n')
    const eventName = this.eventName
    this.dataLines = []
    this.eventName = ''
    this.stopped = this.onFrame(eventName, data)
  }
}

export async function consumeAIEventStream(
  stream: ReadableStream<Uint8Array>,
  requestId: string,
  onEvent: (event: AIStreamEnvelope) => void,
): Promise<AIStreamEnvelope> {
  const reader = stream.getReader()
  const decoder = new TextDecoder()
  let lastSequence = 0
  let totalBytes = 0
  let eventCount = 0
  let terminal: AIStreamEnvelope | null = null
  const parser = new SSEFrameParser(requestId, (eventName, data) => {
    eventCount += 1
    if (eventCount > MAX_SSE_EVENTS) {
      throw new AIClientError('AI 流式响应事件过多，已停止读取。', {
        code: 'AI_SSE_EVENT_LIMIT',
        requestId,
        retryable: true,
      })
    }
    const event = parseEnvelope(data, eventName, requestId)
    if (event.sequence <= lastSequence || terminal) {
      throw new AIClientError('AI 流式事件顺序无效，请重新发起请求。', {
        code: 'AI_INVALID_SSE_SEQUENCE',
        requestId,
        retryable: true,
      })
    }
    lastSequence = event.sequence
    if (event.type === 'error' || event.type === 'response.completed') terminal = event
    onEvent(event)
    return terminal === event
  })

  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) {
        parser.feed(decoder.decode())
        parser.finish()
      } else if (value) {
        totalBytes += value.byteLength
        if (totalBytes > MAX_SSE_RESPONSE_BYTES) {
          throw new AIClientError('AI 流式响应超过安全大小上限，已停止读取。', {
            code: 'AI_SSE_RESPONSE_TOO_LARGE',
            requestId,
            retryable: true,
          })
        }
        parser.feed(decoder.decode(value, { stream: true }))
      }
      if (parser.isStopped) {
        await reader.cancel('AI terminal event received').catch(() => undefined)
        break
      }
      if (done) break
    }
  } catch (error) {
    await reader.cancel(error).catch(() => undefined)
    throw error
  } finally {
    reader.releaseLock()
  }

  if (!terminal) {
    throw new AIClientError('AI 流式响应意外中断，请重新发起请求。', {
      code: 'AI_STREAM_INTERRUPTED',
      requestId,
      retryable: true,
    })
  }
  return terminal as AIStreamEnvelope
}

export async function streamAIResponse(options: AIStreamOptions): Promise<AIStreamEnvelope> {
  const attachments = options.attachments ?? []
  const artifactAttachments = options.artifactAttachments ?? []
  let requestId: string
  try {
    requestId = options.requestId ?? createRequestId()
  } catch (error) {
    clearRequestAttachmentData(attachments)
    throw error
  }
  if (!REQUEST_ID_PATTERN.test(requestId)) {
    clearRequestAttachmentData(attachments)
    throw new AIClientError('请求标识格式无效。', { code: 'AI_INVALID_REQUEST_ID' })
  }
  if (options.conversationId && !/^aicv-[0-9a-f]{32}$/.test(options.conversationId)) {
    clearRequestAttachmentData(attachments)
    throw new AIClientError('会话标识格式无效。', { code: 'AI_INVALID_CONVERSATION_ID' })
  }
  if (attachments.length > 3) {
    clearRequestAttachmentData(attachments)
    throw new AIClientError('每次最多发送 3 张图片。', {
      code: 'AI_ATTACHMENT_COUNT_EXCEEDED',
      requestId,
    })
  }
  if (attachments.length && artifactAttachments.length) {
    clearRequestAttachmentData(attachments)
    throw new AIClientError('不能混合发送原始图片和 Artifact 图片。', {
      code: 'AI_ATTACHMENT_CONTRACT_INVALID',
      requestId,
    })
  }
  const consent = options.cloudProcessingConsent
  const attachmentIds = attachments.map((attachment) => attachment.id)
  const consentAttachmentIds = Array.isArray(consent?.attachment_ids)
    ? consent.attachment_ids
    : []
  const hasExactConsent = consent?.accepted === true
    && consent.notice_version === 'aliyun-cn-beijing-v1'
    && consentAttachmentIds.length === attachmentIds.length
    && consentAttachmentIds.every((id, index) => id === attachmentIds[index])
  if (attachments.length && !hasExactConsent) {
    clearRequestAttachmentData(attachments)
    throw new AIClientError('发送图片前，请先确认同意云端处理。', {
      code: 'AI_CLOUD_PROCESSING_CONSENT_REQUIRED',
      requestId,
    })
  }
  const artifactConsent = options.artifactEgressConsent
  const artifactIds = artifactAttachments.map((attachment) => attachment.artifact_id)
  const exactArtifactConsent = artifactConsent?.accepted === true
    && artifactConsent.notice_version === 'aliyun-cn-beijing-image-v1'
    && artifactConsent.provider === 'qwen'
    && artifactConsent.region === 'cn-beijing'
    && artifactConsent.classification === 'CONFIDENTIAL_BUSINESS'
    && artifactConsent.content_class === 'IMAGE'
    && artifactConsent.artifact_ids.length === artifactIds.length
    && artifactConsent.artifact_ids.every((id, index) => id === artifactIds[index])
  if (artifactAttachments.length && !exactArtifactConsent) {
    throw new AIClientError('发送图片 Artifact 前，请重新确认本次云端处理。', {
      code: 'AI_ARTIFACT_EGRESS_CONSENT_REQUIRED',
      requestId,
    })
  }
  const controller = new AbortController()
  let timedOut = false
  const abortFromCaller = () => controller.abort(options.signal?.reason)
  if (options.signal?.aborted) abortFromCaller()
  options.signal?.addEventListener('abort', abortFromCaller, { once: true })
  const timeout = window.setTimeout(() => {
    timedOut = true
    controller.abort()
  }, options.timeoutMs ?? DEFAULT_STREAM_TIMEOUT_MS)
  const url = `${apiBaseUrl()}/ai/responses`

  try {
    let response: Response
    let requestBody = ''
    try {
      requestBody = JSON.stringify({
        messages: options.messages,
        ...(options.conversationId ? { conversation_id: options.conversationId } : {}),
        page_context: options.pageContext,
        ...(attachments.length
          ? {
              attachments,
              cloud_processing_consent: consent,
            }
          : {}),
        ...(artifactAttachments.length
          ? {
              artifact_attachments: artifactAttachments,
              artifact_egress_consent: artifactConsent,
            }
          : {}),
      })
      response = await fetch(url, {
        method: 'POST',
        credentials: 'include',
        cache: 'no-store',
        headers: {
          Accept: 'text/event-stream',
          'Content-Type': 'application/json',
          'X-Request-ID': requestId,
        },
        body: requestBody,
        signal: controller.signal,
      })
    } finally {
      requestBody = ''
      clearRequestAttachmentData(attachments)
    }
    if (!response.ok) await readErrorResponse(response, requestId)
    const responseRequestId = response.headers.get('x-request-id')
    if (responseRequestId !== requestId) {
      throw new AIClientError('AI 响应关联标识无效，请重新发起请求。', {
        code: 'AI_REQUEST_ID_MISMATCH',
        requestId,
        retryable: true,
      })
    }
    if (!response.headers.get('content-type')?.toLowerCase().startsWith('text/event-stream')) {
      throw new AIClientError('AI 服务未返回流式响应。', {
        code: 'AI_INVALID_CONTENT_TYPE',
        requestId,
        retryable: true,
      })
    }
    if (!response.body) {
      throw new AIClientError('当前浏览器无法读取 AI 流式响应。', {
        code: 'AI_STREAM_UNAVAILABLE',
        requestId,
      })
    }
    return await consumeAIEventStream(response.body, requestId, options.onEvent)
  } catch (error) {
    if (timedOut) {
      throw new AIClientError('AI 响应超时，请稍后重试。', {
        code: 'AI_CLIENT_TIMEOUT',
        requestId,
        retryable: true,
      })
    }
    throw error
  } finally {
    window.clearTimeout(timeout)
    options.signal?.removeEventListener('abort', abortFromCaller)
  }
}
