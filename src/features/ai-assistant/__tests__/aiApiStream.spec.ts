import { afterEach, describe, expect, it, vi } from 'vitest'

const httpMocks = vi.hoisted(() => ({
  get: vi.fn(),
  dispatchAccessFailure: vi.fn(),
}))

vi.mock('@/lib/http', () => ({
  http: { get: httpMocks.get },
  dispatchAccessFailure: httpMocks.dispatchAccessFailure,
}))

import {
  AIClientError,
  consumeAIEventStream,
  getAICapabilities,
  normalizeAIFailure,
  streamAIResponse,
} from '@/api/ai'
import type { AIStreamEnvelope } from '../types'

const requestId = 'web-test-request-1'

function envelope(sequence: number, type: string, payload: Record<string, unknown>) {
  return {
    schema_version: '1',
    request_id: requestId,
    sequence,
    type,
    timestamp: `2026-08-11T00:00:0${sequence}Z`,
    payload,
  }
}

function randomByteStream(source: string) {
  const bytes = new TextEncoder().encode(source)
  const sizes = [1, 7, 2, 11, 3, 5, 13, 4]
  return new ReadableStream<Uint8Array>({
    start(controller) {
      let offset = 0
      let index = 0
      while (offset < bytes.length) {
        const size = sizes[index % sizes.length] ?? 1
        controller.enqueue(bytes.slice(offset, offset + size))
        offset += size
        index += 1
      }
      controller.close()
    },
  })
}

function singleByteStream(source: string) {
  const bytes = new TextEncoder().encode(source)
  return new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(bytes)
      controller.close()
    },
  })
}

function successResponse(body: ReadableStream<Uint8Array>) {
  return new Response(body, {
    status: 200,
    headers: {
      'Content-Type': 'text/event-stream; charset=utf-8',
      'X-Request-ID': requestId,
    },
  })
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.useRealTimers()
  httpMocks.dispatchAccessFailure.mockReset()
  httpMocks.get.mockReset()
})

describe('AI fetch + SSE client', () => {
  it('normalizes the server Pilot contract and fails closed for missing or unknown fields', async () => {
    httpMocks.get.mockResolvedValueOnce({
      data: {
        enabled: true,
        available: true,
        provider: 'aliyun-coding-plan',
        model: 'qwen3.7-plus',
        streaming: true,
        vision_enabled: false,
        conversation_persistence: false,
        tool_groups: ['module_help'],
        pilot_access: { granted: true, status: 'GRANTED', read_only: true },
      },
    })
    await expect(getAICapabilities()).resolves.toMatchObject({
      pilot_access: { granted: true, status: 'GRANTED', read_only: true },
    })
    expect(httpMocks.get).toHaveBeenLastCalledWith('/ai/capabilities', {
      skipForbiddenSessionRefresh: true,
    })

    httpMocks.get.mockResolvedValueOnce({
      data: {
        enabled: true,
        available: false,
        streaming: true,
        pilot_access: { granted: false, status: 'CONTROL_REQUIRED', read_only: true },
      },
    })
    await expect(getAICapabilities()).resolves.toMatchObject({
      pilot_access: { granted: false, status: 'CONTROL_REQUIRED', read_only: true },
    })

    httpMocks.get.mockResolvedValueOnce({
      data: {
        enabled: true,
        available: true,
        streaming: true,
        pilot_access: { granted: true, status: 'future-status', read_only: true },
      },
    })
    await expect(getAICapabilities()).resolves.toMatchObject({
      pilot_access: { granted: true, status: 'UNKNOWN', read_only: true },
    })

    httpMocks.get.mockResolvedValueOnce({ data: { enabled: true, available: true, streaming: true } })
    await expect(getAICapabilities()).resolves.toMatchObject({
      pilot_access: { granted: false, status: 'UNKNOWN', read_only: false },
    })
  })

  it.each([
    ['AI_CONCURRENT_REQUEST_LIMIT', '你已有一个 AI 请求正在处理，请等待完成或先停止。'],
    ['AI_RATE_LIMITED', 'AI 请求较多，请稍后重试。'],
    ['AI_BUDGET_EXCEEDED', '当前 AI 预算额度已用完，请稍后再试或联系管理员。'],
  ])('maps stable guard code %s to a fixed Chinese recovery message', (code, message) => {
    expect(normalizeAIFailure({
      code,
      message: 'provider-or-internal-text-must-not-render',
      retryable: true,
      retry_after_seconds: 30,
    }, 429)).toEqual({
      code,
      message,
      retryable: true,
      retryAfterSeconds: 30,
    })
  })

  it('settles as soon as a terminal frame arrives even when the transport stays open', async () => {
    let streamController: ReadableStreamDefaultController<Uint8Array> | undefined
    let cancelled = false
    const terminalFrame = `event: response.completed\ndata: ${JSON.stringify(envelope(1, 'response.completed', {}))}\n\n`
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        streamController = controller
        controller.enqueue(new TextEncoder().encode(terminalFrame))
      },
      cancel() {
        cancelled = true
      },
    })
    const pending = consumeAIEventStream(stream, requestId, () => undefined)
    const outcome = await Promise.race([
      pending.then(() => 'settled'),
      new Promise<'pending'>((resolve) => window.setTimeout(() => resolve('pending'), 25)),
    ])
    if (outcome === 'pending') {
      streamController?.close()
      await pending
    }

    expect(outcome).toBe('settled')
    expect(cancelled).toBe(true)
    expect(stream.locked).toBe(false)
  })

  it('rejects an oversized SSE line before attempting to parse its JSON', async () => {
    const oversizedLine = `data: ${'x'.repeat(512 * 1024 + 1)}\n\n`
    await expect(consumeAIEventStream(
      singleByteStream(oversizedLine),
      requestId,
      () => undefined,
    )).rejects.toMatchObject({ code: 'AI_SSE_LINE_TOO_LARGE' })
  })

  it('rejects an oversized multi-line SSE frame', async () => {
    const data = 'x'.repeat(400 * 1024)
    const oversizedFrame = `data: ${data}\ndata: ${data}\ndata: ${data}\n\n`
    await expect(consumeAIEventStream(
      singleByteStream(oversizedFrame),
      requestId,
      () => undefined,
    )).rejects.toMatchObject({ code: 'AI_SSE_FRAME_TOO_LARGE' })
  })

  it('rejects streams that exceed the cumulative event limit', async () => {
    const events = Array.from({ length: 4_097 }, (_, index) => (
      `event: message.delta\ndata: ${JSON.stringify(envelope(index + 1, 'message.delta', { delta: 'x' }))}\n\n`
    )).join('')
    await expect(consumeAIEventStream(
      singleByteStream(events),
      requestId,
      () => undefined,
    )).rejects.toMatchObject({ code: 'AI_SSE_EVENT_LIMIT' })
  })

  it('rejects streams that exceed the cumulative byte limit', async () => {
    const bytes = new Uint8Array(8 * 1024 * 1024 + 1)
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes)
        controller.close()
      },
    })
    await expect(consumeAIEventStream(stream, requestId, () => undefined))
      .rejects.toMatchObject({ code: 'AI_SSE_RESPONSE_TOO_LARGE' })
  })

  it('parses random UTF-8 chunk boundaries, CRLF, multi-line data, heartbeat and a trailing terminal frame', async () => {
    const firstJson = JSON.stringify(envelope(1, 'message.delta', { delta: '你好 ' }))
      .replace(',"request_id"', ',\n"request_id"')
    const firstData = firstJson.split('\n').map((line) => `data: ${line}`).join('\r\n')
    const streamText = [
      ': keep-alive\r\n\r\n',
      `event: message.delta\r\n${firstData}\r\n\r\n`,
      `event: message.delta\ndata: ${JSON.stringify(envelope(2, 'message.delta', { delta: '世界' }))}\n\n`,
      `event: response.completed\r\ndata: ${JSON.stringify(envelope(3, 'response.completed', {}))}`,
    ].join('')
    const fetchMock = vi.fn().mockResolvedValue(successResponse(randomByteStream(streamText)))
    vi.stubGlobal('fetch', fetchMock)
    const events: AIStreamEnvelope[] = []

    const terminal = await streamAIResponse({
      requestId,
      messages: [{ role: 'user', content: [{ type: 'input_text', text: '帮助' }] }],
      pageContext: {
        route_name: 'injection-scheduling-v2',
        path: '/modules/production/injection-scheduling',
        factory_id: 'huaxing',
        module_id: 'injection-scheduling',
        selected_entity: null,
      },
      onEvent: (event) => events.push(event),
    })

    expect(events.map((event) => event.type)).toEqual([
      'message.delta',
      'message.delta',
      'response.completed',
    ])
    expect(events.slice(0, 2).map((event) => event.payload.delta).join('')).toBe('你好 世界')
    expect(terminal.type).toBe('response.completed')
    const [, init] = fetchMock.mock.calls[0] ?? []
    expect(init).toMatchObject({ method: 'POST', credentials: 'include', cache: 'no-store' })
    expect(JSON.parse(String((init as RequestInit).body))).toMatchObject({
      page_context: {
        route_name: 'injection-scheduling-v2',
        factory_id: 'huaxing',
        selected_entity: null,
      },
    })
    expect(JSON.parse(String((init as RequestInit).body))).not.toHaveProperty('attachments')
    expect(JSON.parse(String((init as RequestInit).body))).not.toHaveProperty('cloud_processing_consent')
  })

  it('serializes only the approved current-request image contract', async () => {
    const terminalFrame = `event: response.completed\ndata: ${JSON.stringify(envelope(1, 'response.completed', {}))}\n\n`
    const fetchMock = vi.fn().mockResolvedValue(successResponse(singleByteStream(terminalFrame)))
    vi.stubGlobal('fetch', fetchMock)

    const attachment = {
      id: 'image-safe-1',
      media_type: 'image/png' as const,
      data_url: 'data:image/png;base64,iVBORw0KGgo=',
    }
    await streamAIResponse({
      requestId,
      messages: [{ role: 'user', content: [{ type: 'input_text', text: '识别这张截图' }] }],
      pageContext: null,
      attachments: [attachment],
      cloudProcessingConsent: {
        accepted: true,
        notice_version: 'aliyun-cn-beijing-v1',
        attachment_ids: ['image-safe-1'],
      },
      onEvent: () => undefined,
    })

    const [, init] = fetchMock.mock.calls[0] ?? []
    const body = JSON.parse(String((init as RequestInit).body))
    expect(body.attachments).toEqual([{
      id: 'image-safe-1',
      media_type: 'image/png',
      data_url: 'data:image/png;base64,iVBORw0KGgo=',
    }])
    expect(body.cloud_processing_consent).toEqual({
      accepted: true,
      notice_version: 'aliyun-cn-beijing-v1',
      attachment_ids: ['image-safe-1'],
    })
    expect(body.attachments[0]).not.toHaveProperty('source_type')
    expect(body.messages).toEqual([{
      role: 'user',
      content: [{ type: 'input_text', text: '识别这张截图' }],
    }])
    expect(attachment.data_url).toBe('')
  })

  it('releases caller image data after response headers while SSE remains open', async () => {
    let streamController: ReadableStreamDefaultController<Uint8Array> | undefined
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        streamController = controller
      },
    })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(successResponse(stream)))
    const attachment = {
      id: 'image-header-release',
      media_type: 'image/png' as const,
      data_url: 'data:image/png;base64,iVBORw0KGgo=',
    }
    const pending = streamAIResponse({
      requestId,
      messages: [{ role: 'user', content: [{ type: 'input_text', text: '识别' }] }],
      pageContext: null,
      attachments: [attachment],
      cloudProcessingConsent: {
        accepted: true,
        notice_version: 'aliyun-cn-beijing-v1',
        attachment_ids: [attachment.id],
      },
      onEvent: () => undefined,
    })

    await vi.waitFor(() => expect(attachment.data_url).toBe(''))
    const terminalFrame = `event: response.completed\ndata: ${JSON.stringify(envelope(1, 'response.completed', {}))}\n\n`
    streamController?.enqueue(new TextEncoder().encode(terminalFrame))
    await expect(pending).resolves.toMatchObject({ type: 'response.completed' })
  })

  it('fails before fetch when current-batch cloud consent is absent', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    await expect(streamAIResponse({
      requestId,
      messages: [{ role: 'user', content: [{ type: 'input_text', text: '识别' }] }],
      pageContext: null,
      attachments: [{
        id: 'image-safe-1',
        media_type: 'image/png',
        data_url: 'data:image/png;base64,iVBORw0KGgo=',
      }],
      cloudProcessingConsent: null,
      onEvent: () => undefined,
    })).rejects.toMatchObject({ code: 'AI_CLOUD_PROCESSING_CONSENT_REQUIRED' })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('rejects consent whose attachment IDs do not exactly match the current batch', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    await expect(streamAIResponse({
      requestId,
      messages: [{ role: 'user', content: [{ type: 'input_text', text: '识别' }] }],
      pageContext: null,
      attachments: [{
        id: 'image-current',
        media_type: 'image/png',
        data_url: 'data:image/png;base64,iVBORw0KGgo=',
      }],
      cloudProcessingConsent: {
        accepted: true,
        notice_version: 'aliyun-cn-beijing-v1',
        attachment_ids: ['image-stale'],
      },
      onEvent: () => undefined,
    })).rejects.toMatchObject({ code: 'AI_CLOUD_PROCESSING_CONSENT_REQUIRED' })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('clears image data immediately when an HTTP response fails', async () => {
    const attachment = {
      id: 'image-http-failure',
      media_type: 'image/png' as const,
      data_url: 'data:image/png;base64,iVBORw0KGgo=',
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      detail: { code: 'AI_IMAGE_REJECTED', message: '图片未通过服务端校验', retryable: false },
    }), {
      status: 422,
      headers: { 'Content-Type': 'application/json' },
    })))

    await expect(streamAIResponse({
      requestId,
      messages: [{ role: 'user', content: [{ type: 'input_text', text: '识别' }] }],
      pageContext: null,
      attachments: [attachment],
      cloudProcessingConsent: {
        accepted: true,
        notice_version: 'aliyun-cn-beijing-v1',
        attachment_ids: [attachment.id],
      },
      onEvent: () => undefined,
    })).rejects.toMatchObject({ code: 'AI_IMAGE_REJECTED' })
    expect(attachment.data_url).toBe('')
  })

  it('aborts the POST stream when the caller closes the conversation', async () => {
    let requestSignal: AbortSignal | undefined
    const attachment = {
      id: 'image-abort',
      media_type: 'image/png' as const,
      data_url: 'data:image/png;base64,iVBORw0KGgo=',
    }
    vi.stubGlobal('fetch', vi.fn((_url: string, init?: RequestInit) => {
      requestSignal = init?.signal ?? undefined
      return new Promise<Response>((_resolve, reject) => {
        requestSignal?.addEventListener('abort', () => reject(requestSignal?.reason), { once: true })
      })
    }))
    const controller = new AbortController()
    const pending = streamAIResponse({
      requestId,
      messages: [],
      pageContext: null,
      attachments: [attachment],
      cloudProcessingConsent: {
        accepted: true,
        notice_version: 'aliyun-cn-beijing-v1',
        attachment_ids: [attachment.id],
      },
      signal: controller.signal,
      onEvent: () => undefined,
    })

    controller.abort()
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' })
    expect(requestSignal?.aborted).toBe(true)
    expect(attachment.data_url).toBe('')
  })

  it('turns the client deadline into a retryable timeout without reconnecting', async () => {
    vi.useFakeTimers()
    const fetchMock = vi.fn((_url: string, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () => reject(init.signal?.reason), { once: true })
    }))
    vi.stubGlobal('fetch', fetchMock)
    const pending = streamAIResponse({
      requestId,
      messages: [],
      pageContext: null,
      timeoutMs: 25,
      onEvent: () => undefined,
    })
    const assertion = expect(pending).rejects.toMatchObject({
      code: 'AI_CLIENT_TIMEOUT',
      retryable: true,
    })

    await vi.advanceTimersByTimeAsync(26)
    await assertion
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it.each([
    [401, '登录状态已失效，请重新登录。'],
    [403, '当前账号无权使用此 AI 能力。'],
    [429, 'AI 请求较多，请稍后重试。'],
    [500, 'AI 服务暂时不可用，请稍后重试。'],
  ])('maps HTTP %s to a structured safe public error', async (status, expectedMessage) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      detail: { code: `AI_${status}`, message: `public-${status}`, retryable: status >= 429 },
    }), {
      status,
      headers: { 'Content-Type': 'application/json' },
    })))

    await expect(streamAIResponse({
      requestId,
      messages: [],
      pageContext: null,
      onEvent: () => undefined,
    })).rejects.toMatchObject({
      name: 'AIClientError',
      code: `AI_${status}`,
      status,
      message: expectedMessage,
    })

    expect(httpMocks.dispatchAccessFailure).toHaveBeenCalledWith(
      status,
      expect.stringContaining('/ai/responses'),
      expect.anything(),
    )
  })

  it('maps stable Pilot rate and budget codes without exposing server text and bounds retry-after', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      detail: {
        code: 'AI_BUDGET_EXCEEDED',
        message: 'provider-secret-budget-details',
        retryable: true,
        retry_after_seconds: 120,
      },
    }), {
      status: 429,
      headers: { 'Content-Type': 'application/json' },
    })))

    await expect(streamAIResponse({
      requestId,
      messages: [],
      pageContext: null,
      onEvent: () => undefined,
    })).rejects.toMatchObject({
      code: 'AI_BUDGET_EXCEEDED',
      status: 429,
      message: '当前 AI 预算额度已用完，请稍后再试或联系管理员。',
      retryable: true,
      retryAfterSeconds: 120,
    })

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      detail: {
        code: 'AI_RATE_LIMITED',
        message: 'do-not-display',
        retryable: true,
        retry_after_seconds: 86_400,
      },
    }), { status: 429, headers: { 'Content-Type': 'application/json' } })))
    await expect(streamAIResponse({
      requestId,
      messages: [],
      pageContext: null,
      onEvent: () => undefined,
    })).rejects.toMatchObject({ retryAfterSeconds: undefined })
  })

  it('rejects a stream that ends without exactly one terminal event', async () => {
    const incomplete = `event: message.delta\ndata: ${JSON.stringify(envelope(1, 'message.delta', { delta: 'partial' }))}\n\n`
    await expect(consumeAIEventStream(
      randomByteStream(incomplete),
      requestId,
      () => undefined,
    )).rejects.toEqual(expect.objectContaining<Partial<AIClientError>>({
      code: 'AI_STREAM_INTERRUPTED',
    }))
  })
})
