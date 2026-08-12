import { computed, reactive, ref } from 'vue'
import { defineStore } from 'pinia'
import { productionFactoryContextIds } from '@/data/enterpriseMock'
import {
  AIClientError,
  getAICapabilities,
  normalizeAIFailure,
  streamAIResponse,
} from '@/api/ai'
import type {
  AIBusinessResult,
  AICapabilities,
  AIChatRequestMessage,
  AICloudProcessingConsent,
  AIConversationMessage,
  AIEntityLink,
  AIFailure,
  AIPageContext,
  AIRequestAttachment,
  AIInternalQuoteSummary,
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
const INTERNAL_LINK_PATTERN = /^\/(?:modules(?:\/|$)|tools(?:\/|$)|workbench(?:\/|$))/
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

function bool(value: unknown) {
  return value === true
}

function finiteNumber(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function boundedText(value: unknown, minLength: number, maxLength: number) {
  if (typeof value !== 'string') return null
  const normalized = value.trim()
  return normalized.length >= minLength && normalized.length <= maxLength
    ? normalized
    : null
}

function boundedInteger(value: unknown, minimum: number, maximum: number) {
  return typeof value === 'number'
    && Number.isInteger(value)
    && value >= minimum
    && value <= maximum
    ? value
    : null
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]) {
  const actual = Object.keys(value)
  return actual.length === keys.length && actual.every((key) => keys.includes(key))
}

function safeLinks(value: unknown): AIEntityLink[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((item) => {
    const source = record(item)
    if (!source) return []
    const route = text(source.route, 300)
    if (!INTERNAL_LINK_PATTERN.test(route)) return []
    const rawQuery = record(source.query)
    const query = rawQuery
      ? Object.fromEntries(
          Object.entries(rawQuery)
            .filter((entry): entry is [string, string] => typeof entry[1] === 'string')
            .map(([key, itemValue]) => [key.slice(0, 64), itemValue.slice(0, 128)]),
        )
      : undefined
    return [{
      label: text(source.label, 100) || '打开业务页面',
      route,
      ...(query && Object.keys(query).length ? { query } : {}),
    }]
  })
}

function sourceLevel(value: unknown): AISourceSummary['level'] {
  const normalized = text(value, 40).toUpperCase()
  if (normalized === 'VERSIONED_MODULE_KNOWLEDGE') return 'MODULE_KNOWLEDGE'
  return ['FORMAL', 'MODULE_KNOWLEDGE', 'USER_PROVIDED', 'MODEL_INFERENCE'].includes(normalized)
    ? normalized as AISourceSummary['level']
    : 'UNKNOWN'
}

function sourceLabel(level: AISourceSummary['level']) {
  return {
    FORMAL: '系统正式数据',
    MODULE_KNOWLEDGE: '受控页面知识',
    USER_PROVIDED: '用户提供内容',
    MODEL_INFERENCE: '模型推断',
    UNKNOWN: '来源待确认',
  }[level]
}

function extractSource(value: unknown): AISourceSummary | null {
  if (typeof value === 'string') {
    const normalized = value.trim().toUpperCase()
    if (!['USER_PROVIDED', 'MODEL_INFERENCE'].includes(normalized)) return null
    const level = normalized as 'USER_PROVIDED' | 'MODEL_INFERENCE'
    return {
      id: localId('source'),
      level,
      label: sourceLabel(level),
      links: [],
    }
  }
  const source = record(value)
  if (!source) return null
  const level = sourceLevel(source.source_type ?? source.level)
  const factoryId = text(source.factory_id, 64)
  const updatedAt = text(source.as_of ?? source.updated_at ?? source.last_reviewed_at, 80)
  const label = text(source.source_label, 120) || sourceLabel(level)
  const links = safeLinks(source.entity_links ?? source.links)
  if (level === 'UNKNOWN' && !factoryId && !updatedAt && !links.length) return null
  return {
    id: localId('source'),
    level,
    label,
    ...(factoryId ? { factoryId } : {}),
    ...(updatedAt ? { updatedAt } : {}),
    links,
  }
}

const INTERNAL_QUOTE_STATUS_CONTRACT: Record<string, {
  statusLabel: string
  stageCode: string
  stageLabel: string
  navigationTarget: 'collaboration' | 'summary'
}> = {
  drafting: {
    statusLabel: '协作草稿', stageCode: 'COLLABORATION', stageLabel: '分段协作填写', navigationTarget: 'collaboration',
  },
  section_reviewing: {
    statusLabel: '待分段审核', stageCode: 'SECTION_REVIEW', stageLabel: '分段审核', navigationTarget: 'collaboration',
  },
  pending_review: {
    statusLabel: '待分段审核', stageCode: 'SECTION_REVIEW', stageLabel: '分段审核', navigationTarget: 'collaboration',
  },
  rejected: {
    statusLabel: '已退回', stageCode: 'RETURNED', stageLabel: '退回后修正', navigationTarget: 'collaboration',
  },
  ready_for_final_review: {
    statusLabel: '待最终提交', stageCode: 'FINAL_SUBMISSION', stageLabel: '等待提交最终放行', navigationTarget: 'summary',
  },
  final_reviewing: {
    statusLabel: '待最终放行', stageCode: 'FINAL_REVIEW', stageLabel: '等待负责跟客确认放行', navigationTarget: 'summary',
  },
  fully_approved: {
    statusLabel: '已放行', stageCode: 'RELEASED', stageLabel: '最终放行已通过', navigationTarget: 'summary',
  },
  exported: {
    statusLabel: '已导出', stageCode: 'EXPORTED', stageLabel: '受控文件已导出', navigationTarget: 'summary',
  },
  archived: {
    statusLabel: '已归档', stageCode: 'ARCHIVED', stageLabel: '报价已归档', navigationTarget: 'collaboration',
  },
  unknown: {
    statusLabel: '状态待确认', stageCode: 'UNKNOWN', stageLabel: '请在内部报价台核对', navigationTarget: 'collaboration',
  },
}

function isInternalQuoteResultCandidate(source: Record<string, unknown>) {
  const resultType = typeof source.result_type === 'string' ? source.result_type : ''
  const schemaVersion = typeof source.schema_version === 'string' ? source.schema_version : ''
  return resultType === 'internal_quote'
    || resultType.startsWith('internal_quote.')
    || schemaVersion === 'internal-quote'
    || schemaVersion.startsWith('internal-quote-')
    || Object.hasOwn(source, 'quotes')
}

function extractInternalQuoteResult(
  source: Record<string, unknown>,
): AIBusinessResult | null {
  if (!hasExactKeys(source, [
    'schema_version',
    'result_type',
    'source_type',
    'factory_id',
    'as_of',
    'total',
    'limit',
    'offset',
    'returned',
    'truncated',
    'quotes',
  ])) return null
  if (
    source.result_type !== 'internal_quote.summary_list'
    || source.schema_version !== 'internal-quote-summary-v1'
    || source.source_type !== 'FORMAL'
  ) return null
  const factoryId = boundedText(source.factory_id, 1, 64)
  const asOf = boundedText(source.as_of, 1, 40)
  const total = boundedInteger(source.total, 0, Number.MAX_SAFE_INTEGER)
  const returned = boundedInteger(source.returned, 0, 20)
  const limit = boundedInteger(source.limit, 1, 20)
  const offset = boundedInteger(source.offset, 0, 10_000)
  const rawQuotes = Array.isArray(source.quotes) ? source.quotes : null
  if (
    !factoryId
    || !productionFactoryContextIds.includes(factoryId as (typeof productionFactoryContextIds)[number])
    || !asOf
    || total === null
    || returned === null
    || limit === null
    || offset === null
    || rawQuotes === null
    || rawQuotes.length > 20
    || returned !== rawQuotes.length
    || total < returned
    || typeof source.truncated !== 'boolean'
    || source.truncated !== (offset + returned < total)
  ) return null

  const quotes: AIInternalQuoteSummary[] = []
  for (const rawQuote of rawQuotes) {
    const quote = record(rawQuote)
    if (!quote || !hasExactKeys(quote, [
      'quote_id',
      'quote_no',
      'customer',
      'status_code',
      'status_label',
      'current_stage_code',
      'current_stage_label',
      'version_label',
      'updated_at',
      'navigation_target',
    ])) return null
    const quoteId = boundedText(quote.quote_id, 1, 64)
    const quoteNo = boundedText(quote.quote_no, 1, 128)
    const customer = boundedText(quote.customer, 0, 128)
    const statusCode = boundedText(quote.status_code, 1, 32)
    const versionLabel = boundedText(quote.version_label, 0, 64)
    const updatedAt = boundedText(quote.updated_at, 0, 32)
    const policy = statusCode ? INTERNAL_QUOTE_STATUS_CONTRACT[statusCode] : undefined
    if (
      !quoteId
      || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(quoteId)
      || !quoteNo
      || customer === null
      || !statusCode
      || !policy
      || quote.status_label !== policy.statusLabel
      || quote.current_stage_code !== policy.stageCode
      || quote.current_stage_label !== policy.stageLabel
      || quote.navigation_target !== policy.navigationTarget
      || versionLabel === null
      || updatedAt === null
    ) return null
    quotes.push({
      quoteId,
      quoteNo,
      customer,
      statusCode,
      statusLabel: policy.statusLabel,
      currentStageCode: policy.stageCode,
      currentStageLabel: policy.stageLabel,
      versionLabel,
      updatedAt,
      navigationTarget: policy.navigationTarget,
    })
  }

  return {
    id: localId('result'),
    kind: 'internal_quote_list',
    title: '内部报价摘要',
    summary: `本次返回 ${returned} 条，共 ${total} 条。`,
    sourceType: 'FORMAL',
    factoryId,
    asOf,
    truncated: source.truncated,
    links: [],
    internalQuote: { total, returned, limit, offset, quotes },
  }
}

function extractBusinessResult(value: unknown): AIBusinessResult | null {
  const source = record(value)
  if (!source) return null
  if (isInternalQuoteResultCandidate(source)) return extractInternalQuoteResult(source)
  const sourceType = text(source.source_type, 64)
  const rawSummary = source.summary ?? source.description ?? source.answer ?? source.help_markdown
  const summary = text(rawSummary, 4_000)
  const links = safeLinks(source.entity_links ?? source.links)
  const factoryId = text(source.factory_id, 64)
  const asOf = text(source.as_of ?? source.updated_at, 80)
  const executionPublished = record(source.execution_published)
  const planningDraft = record(source.planning_draft)
  const isPlanContext = 'execution_published' in source || 'planning_draft' in source
  const backlogItems = Array.isArray(source.items)
    ? source.items
    : Array.isArray(source.orders)
      ? source.orders
      : null
  const isBacklog = backlogItems !== null
    || finiteNumber(source.total) !== undefined
    || finiteNumber(source.returned) !== undefined
  if (!sourceType && !summary && !links.length && !isPlanContext && !isBacklog) return null

  const planSummary = (plan: Record<string, unknown> | null) => plan
    ? {
        ...(text(plan.plan_id, 128) ? { planId: text(plan.plan_id, 128) } : {}),
        ...(text(plan.business_date, 40) ? { businessDate: text(plan.business_date, 40) } : {}),
        ...(finiteNumber(plan.revision) !== undefined ? { revision: finiteNumber(plan.revision) } : {}),
        ...(finiteNumber(plan.task_count) !== undefined ? { taskCount: finiteNumber(plan.task_count) } : {}),
        ...(finiteNumber(plan.running_count) !== undefined ? { runningCount: finiteNumber(plan.running_count) } : {}),
      }
    : null

  return {
    id: localId('result'),
    kind: isPlanContext ? 'plan_context' : isBacklog ? 'backlog' : 'generic',
    title: text(source.title ?? source.module_name, 120) || (isPlanContext
      ? '注塑排产状态'
      : isBacklog
        ? '注塑待排订单'
        : sourceType === 'FORMAL'
          ? '业务数据摘要'
          : '页面帮助'),
    summary,
    sourceType: sourceType || 'UNKNOWN',
    ...(factoryId ? { factoryId } : {}),
    ...(asOf ? { asOf } : {}),
    truncated: bool(source.truncated)
      || (typeof rawSummary === 'string' && rawSummary.trim().length > 4_000),
    links,
    ...(isPlanContext
      ? {
          planContext: {
            executionPublished: planSummary(executionPublished),
            planningDraft: planSummary(planningDraft),
            ...(finiteNumber(source.polling_revision) !== undefined
              ? { pollingRevision: finiteNumber(source.polling_revision) }
              : {}),
          },
        }
      : {}),
    ...(isBacklog
      ? {
          backlog: {
            ...(finiteNumber(source.total) !== undefined ? { total: finiteNumber(source.total) } : {}),
            ...(finiteNumber(source.returned) !== undefined
              ? { returned: finiteNumber(source.returned) }
              : backlogItems
                ? { returned: backlogItems.length }
                : {}),
            ...(text(source.source_scope, 120) ? { sourceScope: text(source.source_scope, 120) } : {}),
            ...(text(source.source_business_label, 120)
              ? { sourceBusinessLabel: text(source.source_business_label, 120) }
              : {}),
          },
        }
      : {}),
  }
}

function toolResultData(value: unknown) {
  const result = record(value)
  return result ? result.data : undefined
}

function toolActivityLabel(toolName: string) {
  if (toolName.startsWith('internal_quote.')) return '正在读取内部报价摘要'
  if (toolName.startsWith('injection_scheduling.')) return '正在读取排产信息'
  if (toolName.startsWith('knowledge.')) return '正在读取页面帮助'
  if (toolName.startsWith('identity.')) return '正在核对当前上下文'
  return '正在读取已授权信息'
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
    && capabilities.value.pilot_access.read_only
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

  function clearConversation() {
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

  function resetForSession() {
    clearConversation()
    isOpen.value = false
    invalidateCapabilities()
  }

  function openDrawer() {
    if (canUse.value) isOpen.value = true
  }

  function closeDrawer() {
    clearConversation()
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
    const toolResult = toolResultData(event.payload.tool_result)
    const result = toolResultData(event.payload.result)
    for (const value of [toolResult, result]) {
      const source = record(value)
      const businessResult = extractBusinessResult(value)
      if (!source || !isInternalQuoteResultCandidate(source) || businessResult) {
        addSource(extractSource(value))
      }
      addBusinessResult(businessResult)
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
    const history = requestHistory()
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
    activeHadAttachments = attachments.length > 0
    status.value = 'streaming'

    try {
      const terminal = await streamAIResponse({
        messages: history,
        pageContext,
        attachments,
        cloudProcessingConsent,
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
          }, attachments.length ? '' : normalized)
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
        recordFailure(failure, failure.retryable && !attachments.length ? normalized : '')
      } else {
        recordFailure({
          code: 'AI_STREAM_INTERRUPTED',
          message: 'AI 连接意外中断，请重新发起请求。',
          retryable: true,
        }, attachments.length ? '' : normalized)
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
    canUse,
    isStreaming,
    canRetry,
    loadCapabilities,
    cancelActiveRequest,
    clearConversation,
    resetForSession,
    openDrawer,
    closeDrawer,
    sendMessage,
    retryLastTextRequest,
  }
})
