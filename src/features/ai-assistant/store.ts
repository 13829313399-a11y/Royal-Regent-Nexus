import { computed, reactive, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  AIClientError,
  getAICapabilities,
  normalizeAIFailure,
  streamAIResponse,
} from '@/api/ai'
import type {
  AIConversationMessage as AIPersistedConversationMessage,
  AIConversationMode,
} from '@/api/aiConversations'
import { extractSource, toolActivityLabel } from './renderers/contracts'
import { rendererRegistry } from './renderers/registry'
import type {
  AIBusinessResult,
  AIArtifactAttachmentReference,
  AIArtifactEgressConsent,
  AICapabilities,
  AIChatRequestMessage,
  AICloudProcessingConsent,
  AIConversationMessage,
  AIFailure,
  AIPageContext,
  AIRequestAttachment,
  AISourceSummary,
  AIStreamEnvelope,
  AIToolActivityItem,
} from './types'

const MAX_CONVERSATION_MESSAGES = 12
const MAX_MESSAGE_CHARS = 8_000
const MAX_TOTAL_INPUT_CHARS = 40_000
const MAX_TOOL_ACTIVITIES = 8
const MAX_SOURCES = 12
const MAX_BUSINESS_RESULTS = 8
const TRUNCATED_RESPONSE_MESSAGE = '回答过长，后续内容未显示。请缩小问题范围后重试。'
const CAPABILITY_INVALIDATING_ERROR_CODES = new Set([
  'AI_DISABLED',
  'AI_NOT_CONFIGURED',
  'AI_PILOT_ACCESS_DENIED',
  'AI_PROVIDER_AUTHENTICATION_FAILED',
])

let localIdSequence = 0

function localId(prefix: string) {
  localIdSequence += 1
  return `${prefix}-${Date.now()}-${localIdSequence}`
}

function text(value: unknown, maxLength = 1_000) {
  return typeof value === 'string' ? value.trim().slice(0, maxLength) : ''
}

function streamText(value: unknown) {
  return typeof value === 'string' ? value : ''
}

function publicStreamFailure(event: AIStreamEnvelope) {
  return normalizeAIFailure(event.payload)
}

export const useAIAssistantStore = defineStore('aiAssistant', () => {
  const capabilities = ref<AICapabilities | null>(null)
  const capabilitiesLoading = ref(false)
  const isOpen = ref(false)
  const status = ref<'idle' | 'streaming' | 'error'>('idle')
  const messages = ref<AIConversationMessage[]>([])
  const activities = ref<AIToolActivityItem[]>([])
  const sources = ref<AISourceSummary[]>([])
  const businessResults = ref<AIBusinessResult[]>([])
  const lastError = ref('')
  const lastFailure = ref<AIFailure | null>(null)
  const retryPrompt = ref('')
  const activeConversationId = ref<string | null>(null)
  const activeConversationMode = ref<AIConversationMode | null>(null)
  let activeController: AbortController | null = null
  let activeAssistant: AIConversationMessage | null = null
  let activePrompt = ''
  let activeHadAttachments = false
  let conversationGeneration = 0
  let capabilitiesGeneration = 0
  let capabilitiesRequest: Promise<void> | null = null

  const canUse = computed(() => Boolean(
    capabilities.value?.enabled
    && capabilities.value.available
    && capabilities.value.streaming
    && capabilities.value.pilot_access?.granted
    && (
      capabilities.value.pilot_access.max_tool_risk_level === 'PREVIEW_WITH_AUDIT'
      || capabilities.value.pilot_access.max_tool_risk_level === 'READ_ONLY'
      || (
        capabilities.value.pilot_access.max_tool_risk_level === undefined
        && capabilities.value.pilot_access.read_only
      )
    )
    && capabilities.value.pilot_access.status === 'GRANTED',
  ))
  const isStreaming = computed(() => status.value === 'streaming')
  const canRetry = computed(() => Boolean(retryPrompt.value && !isStreaming.value && canUse.value))

  function loadCapabilities(force = false): Promise<void> {
    if (capabilitiesRequest) return capabilitiesRequest
    if (capabilities.value && !force) return Promise.resolve()
    const generation = ++capabilitiesGeneration
    capabilitiesLoading.value = true
    const request = (async () => {
      try {
        const next = await getAICapabilities()
        if (generation === capabilitiesGeneration) capabilities.value = next
      } catch {
        if (generation === capabilitiesGeneration) capabilities.value = null
      } finally {
        if (generation === capabilitiesGeneration) capabilitiesLoading.value = false
      }
    })()
    capabilitiesRequest = request
    void request.finally(() => {
      if (capabilitiesRequest === request) capabilitiesRequest = null
    })
    return request
  }

  function clearActiveRequest() {
    activeController = null
    activeAssistant = null
    activePrompt = ''
    activeHadAttachments = false
  }

  function abortForReset() {
    activeController?.abort()
    clearActiveRequest()
  }

  function failureMessage(failure: AIFailure) {
    return failure.retryAfterSeconds
      ? `${failure.message} 建议 ${failure.retryAfterSeconds} 秒后再试。`
      : failure.message
  }

  function invalidateCapabilities() {
    capabilitiesGeneration += 1
    capabilities.value = null
    capabilitiesLoading.value = false
    capabilitiesRequest = null
  }

  function recordFailure(failure: AIFailure, failedPrompt = '') {
    lastFailure.value = failure
    lastError.value = failureMessage(failure)
    retryPrompt.value = failure.retryable ? failedPrompt : ''
    if (CAPABILITY_INVALIDATING_ERROR_CODES.has(failure.code)) invalidateCapabilities()
  }

  function reportClientError(message: string) {
    lastFailure.value = null
    lastError.value = message
    retryPrompt.value = ''
    status.value = 'error'
  }

  function cancelActiveRequest() {
    const controller = activeController
    if (!controller || status.value !== 'streaming') return false
    const assistant = activeAssistant
    const cancelledPrompt = activePrompt
    const canRetryCancelledPrompt = !activeHadAttachments
    controller.abort()
    clearActiveRequest()
    if (assistant?.status === 'streaming') {
      assistant.status = 'cancelled'
      if (!assistant.text) assistant.text = '已停止生成。'
    }
    activities.value = activities.value.filter((item) => item.status !== 'running')
    status.value = 'idle'
    lastFailure.value = null
    lastError.value = ''
    retryPrompt.value = canRetryCancelledPrompt ? cancelledPrompt : ''
    return true
  }


  function clearPresentation() {
    conversationGeneration += 1
    abortForReset()
    status.value = 'idle'
    messages.value = []
    activities.value = []
    sources.value = []
    businessResults.value = []
    lastError.value = ''
    lastFailure.value = null
    retryPrompt.value = ''
  }

  function clearConversation() {
    clearPresentation()
    activeConversationId.value = null
    activeConversationMode.value = null
  }

  function bindConversation(
    conversationId: string,
    mode: AIConversationMode,
    persistedMessages?: readonly AIPersistedConversationMessage[],
  ) {
    if (activeConversationId.value !== conversationId) clearPresentation()
    activeConversationId.value = conversationId
    activeConversationMode.value = mode
    if (persistedMessages) {
      messages.value = persistedMessages.map((message) => ({
        id: message.id,
        role: message.role === 'USER' ? 'user' : 'assistant',
        text: message.text,
        status: message.truncated ? 'truncated' : 'complete',
        createdAt: message.created_at,
        ...(message.role === 'ASSISTANT'
          ? { feedbackTarget: { type: 'MESSAGE' as const, id: message.id } }
          : {}),
      }))
    }
  }

  function resetForSession() {
    clearConversation()
    isOpen.value = false
    invalidateCapabilities()
  }

  function openDrawer() {
    if (canUse.value) isOpen.value = true
  }

  function closeDrawer() {
    if (activeConversationMode.value !== 'PERSISTENT') clearConversation()
    isOpen.value = false
  }

  function addSource(candidate: AISourceSummary | null) {
    if (!candidate) return
    const key = `${candidate.level}|${candidate.factoryId ?? ''}|${candidate.updatedAt ?? ''}|${candidate.label}`
    if (sources.value.some((item) => `${item.level}|${item.factoryId ?? ''}|${item.updatedAt ?? ''}|${item.label}` === key)) return
    if (sources.value.length < MAX_SOURCES) sources.value.push(candidate)
  }

  function addBusinessResult(candidate: AIBusinessResult | null) {
    if (!candidate) return
    const resultKey = (item: AIBusinessResult) => [
      item.kind,
      item.sourceType,
      item.factoryId ?? '',
      item.asOf ?? '',
      item.summary,
      item.planContext?.executionPublished?.planId ?? '',
      item.planContext?.planningDraft?.planId ?? '',
      item.backlog?.sourceScope ?? '',
      item.backlog?.total ?? '',
      item.backlog?.returned ?? '',
      item.internalQuote?.total ?? '',
      item.internalQuote?.quotes[0]?.quoteId ?? '',
      item.moldingSample?.total ?? '',
      item.moldingSample?.orders[0]?.orderId ?? '',
      item.cartonProcurement?.total ?? '',
      item.cartonProcurement?.orders[0]?.orderId ?? '',
      item.rawMaterialMaster?.total ?? '',
      item.rawMaterialMaster?.materials[0]?.materialId ?? '',
      item.rawMaterialInventory?.total ?? '',
      item.rawMaterialInventory?.batches[0]?.batchId ?? '',
    ].join('|')
    const key = resultKey(candidate)
    if (businessResults.value.some((item) => resultKey(item) === key)) return
    if (businessResults.value.length < MAX_BUSINESS_RESULTS) businessResults.value.push(candidate)
  }

  function updateToolActivity(event: AIStreamEnvelope) {
    if (!event.type.startsWith('tool.')) return
    const callId = text(event.payload.tool_call_id ?? event.payload.call_id, 128)
      || `${event.request_id}-${event.sequence}`
    const toolName = text(event.payload.tool_name ?? event.payload.name, 160)
    const existing = activities.value.find((item) => item.id === callId)
    const payloadStatus = text(event.payload.status, 40).toLowerCase()
    const nextStatus = ['failed', 'error', 'denied', 'timed_out'].includes(payloadStatus)
      || event.type.endsWith('failed')
      || event.type.endsWith('error')
      ? 'error'
      : payloadStatus === 'completed'
        || payloadStatus === 'success'
        || event.type.endsWith('completed')
        || event.type.endsWith('done')
        ? 'complete'
        : 'running'
    if (existing) {
      existing.status = nextStatus
      return
    }
    if (activities.value.length >= MAX_TOOL_ACTIVITIES) return
    activities.value.push({
      id: callId,
      label: toolActivityLabel(toolName),
      status: nextStatus,
    })
  }

  function applyStreamEvent(event: AIStreamEnvelope, assistant: AIConversationMessage) {
    updateToolActivity(event)
    addSource(extractSource(event.payload.source))
    addSource(extractSource(event.payload.input_source))
    if (Array.isArray(event.payload.sources)) {
      event.payload.sources.forEach((item) => addSource(extractSource(item)))
    }
    for (const value of [event.payload.tool_result, event.payload.result]) {
      const rendered = rendererRegistry.renderEnvelope(value)
      if (!rendered) continue
      rendered.sources.forEach((item) => addSource(item))
      addBusinessResult(rendered.businessResult)
    }
    if (event.type === 'message.delta') {
      const delta = streamText(event.payload.delta)
      const remaining = Math.max(MAX_MESSAGE_CHARS - assistant.text.length, 0)
      assistant.text += delta.slice(0, remaining)
      if (delta.length > remaining) assistant.status = 'truncated'
    } else if (event.type === 'message.completed') {
      if (assistant.status !== 'truncated') assistant.status = 'complete'
    } else if (event.type === 'error') {
      assistant.status = 'error'
      const failure = publicStreamFailure(event)
      if (!assistant.text) assistant.text = failure.message
      recordFailure(failure)
      status.value = 'error'
    } else if (event.type === 'response.completed') {
      if (assistant.status !== 'truncated') assistant.status = 'complete'
      const conversation = event.payload.conversation
      const persistedMessageId = conversation
        && typeof conversation === 'object'
        && !Array.isArray(conversation)
        && (conversation as Record<string, unknown>).assistant_persisted === true
        ? text((conversation as Record<string, unknown>).assistant_message_id, 64)
        : ''
      assistant.feedbackTarget = persistedMessageId
        ? { type: 'MESSAGE', id: persistedMessageId }
        : { type: 'RESPONSE', id: event.request_id }
    }
  }

  function requestHistory(): AIChatRequestMessage[] {

    const candidates = messages.value
      .filter((message) => message.text.trim() && message.status === 'complete')
      .slice(-MAX_CONVERSATION_MESSAGES)
    const selected: AIConversationMessage[] = []
    let remainingChars = MAX_TOTAL_INPUT_CHARS
    for (let index = candidates.length - 1; index >= 0; index -= 1) {
      const candidate = candidates[index]
      if (!candidate) continue
      const candidateText = candidate.text.trim()
      if (candidateText.length > remainingChars) break
      selected.push(candidate)
      remainingChars -= candidateText.length
    }
    return selected.reverse().map((message) => ({
      role: message.role,
      content: [{ type: 'input_text', text: message.text.trim() }],
    }))
  }

  async function sendMessage(
    prompt: string,
    pageContext: AIPageContext | null,
    attachments: readonly AIRequestAttachment[] = [],
    cloudProcessingConsent: AICloudProcessingConsent | null = null,
    artifactAttachments: readonly AIArtifactAttachmentReference[] = [],
    artifactEgressConsent: AIArtifactEgressConsent | null = null,
  ) {
    const normalized = prompt.trim()
    if (!normalized || isStreaming.value || !canUse.value) return false
    if (normalized.length > MAX_MESSAGE_CHARS) {
      lastFailure.value = null
      retryPrompt.value = ''
      lastError.value = `单条消息不能超过 ${MAX_MESSAGE_CHARS} 个字符。`
      status.value = 'error'
      return false
    }
    if (attachments.length && !cloudProcessingConsent?.accepted) {
      lastFailure.value = null
      retryPrompt.value = ''
      lastError.value = '发送图片前，请先确认同意云端处理。'
      status.value = 'error'
      return false
    }
    if (artifactAttachments.length && !artifactEgressConsent?.accepted) {
      lastFailure.value = null
      retryPrompt.value = ''
      lastError.value = '发送图片 Artifact 前，请重新确认本次云端处理。'
      status.value = 'error'
      return false
    }
    if (attachments.length && artifactAttachments.length) {
      lastFailure.value = null
      retryPrompt.value = ''
      lastError.value = '不能混合发送原始图片和 Artifact 图片。'
      status.value = 'error'
      return false
    }

    lastError.value = ''
    lastFailure.value = null
    retryPrompt.value = ''
    activities.value = []
    sources.value = []
    businessResults.value = []
    messages.value.push({
      id: localId('user'),
      role: 'user',
      text: normalized,
      status: 'complete',
      createdAt: new Date().toISOString(),
    })
    messages.value = messages.value.slice(-(MAX_CONVERSATION_MESSAGES - 1))
    const history = activeConversationId.value
      ? [{ role: 'user' as const, content: [{ type: 'input_text' as const, text: normalized }] }]
      : requestHistory()
    const assistant = reactive<AIConversationMessage>({
      id: localId('assistant'),
      role: 'assistant',
      text: '',
      status: 'streaming',
      createdAt: new Date().toISOString(),
    })
    messages.value.push(assistant)
    const generation = conversationGeneration
    const controller = new AbortController()
    activeController = controller
    activeAssistant = assistant
    activePrompt = normalized
    activeHadAttachments = attachments.length > 0 || artifactAttachments.length > 0
    status.value = 'streaming'

    try {
      const terminal = await streamAIResponse({
        messages: history,
        ...(activeConversationId.value ? { conversationId: activeConversationId.value } : {}),
        pageContext,
        attachments,
        cloudProcessingConsent,
        artifactAttachments,
        artifactEgressConsent,
        signal: controller.signal,
        onEvent: (event) => {
          if (generation !== conversationGeneration || controller.signal.aborted) return
          applyStreamEvent(event, assistant)
        },
      })
      if (generation !== conversationGeneration || controller.signal.aborted) return false
      if (terminal.type === 'response.completed') {
        if (assistant.status === 'truncated') {
          recordFailure({
            code: 'AI_RESPONSE_TRUNCATED',
            message: TRUNCATED_RESPONSE_MESSAGE,
            retryable: true,
          }, activeHadAttachments ? '' : normalized)
          status.value = 'error'
          return false
        }
        if (!assistant.text) assistant.text = 'AI 已完成响应，但没有返回可显示的文本。'
        assistant.status = 'complete'
        lastFailure.value = null
        lastError.value = ''
        retryPrompt.value = ''
        status.value = 'idle'
        return true
      }
      if (terminal.type === 'error') {
        const failure = normalizeAIFailure(terminal.payload)
        recordFailure(failure, failure.retryable && !activeHadAttachments ? normalized : '')
      } else {
        recordFailure({
          code: 'AI_STREAM_INTERRUPTED',
          message: 'AI 连接意外中断，请重新发起请求。',
          retryable: true,
        }, activeHadAttachments ? '' : normalized)
      }
      status.value = 'error'
      return false
    } catch (error) {
      if (generation !== conversationGeneration || controller.signal.aborted) return false
      const failure: AIFailure = error instanceof AIClientError
        ? {
            code: error.code,
            message: error.message,
            retryable: error.retryable,
            ...(error.retryAfterSeconds !== undefined
              ? { retryAfterSeconds: error.retryAfterSeconds }
              : {}),
          }
        : {
            code: 'AI_STREAM_INTERRUPTED',
            message: 'AI 连接意外中断，请重新发起请求。',
            retryable: true,
          }
      assistant.status = 'error'
      if (!assistant.text) assistant.text = failure.message
      recordFailure(failure, attachments.length ? '' : normalized)
      if (error instanceof AIClientError && error.status === 403) invalidateCapabilities()
      status.value = 'error'
      return false
    } finally {
      if (activeController === controller) clearActiveRequest()

    }
  }

  async function retryLastTextRequest(pageContext: AIPageContext | null) {
    const prompt = retryPrompt.value
    if (!prompt || isStreaming.value || !canUse.value) return false
    const assistantIndex = messages.value.length - 1
    const assistant = messages.value[assistantIndex]
    const user = messages.value[assistantIndex - 1]
    if (
      assistant
      && user
      && assistant.role === 'assistant'
      && ['error', 'cancelled', 'truncated'].includes(assistant.status)
      && user.role === 'user'
      && user.text.trim() === prompt
    ) {
      messages.value.splice(assistantIndex - 1, 2)
    }
    retryPrompt.value = ''
    return sendMessage(prompt, pageContext)
  }

  return {
    capabilities,
    capabilitiesLoading,
    isOpen,
    status,
    messages,
    activities,
    sources,
    businessResults,
    lastError,
    lastFailure,
    activeConversationId,
    activeConversationMode,
    canUse,
    isStreaming,
    canRetry,
    loadCapabilities,
    reportClientError,
    cancelActiveRequest,
    clearConversation,
    bindConversation,
    resetForSession,
    openDrawer,
    closeDrawer,
    sendMessage,
    retryLastTextRequest,
  }
})
