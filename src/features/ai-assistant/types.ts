export type AIPilotAccessStatus =
  | 'DISABLED'
  | 'TLS_REQUIRED'
  | 'CONTROL_REQUIRED'
  | 'PROVIDER_REQUIRED'
  | 'GRANTED'
  | 'UNKNOWN'

export interface AICapabilities {
  enabled: boolean
  available: boolean
  provider: string
  model: string
  streaming: boolean
  vision_enabled: boolean
  conversation_persistence: false
  tool_groups: string[]
  pilot_access: {
    granted: boolean
    status: AIPilotAccessStatus
    read_only: boolean
  }
}

export interface AIInjectionSchedulingPageContext {
  route_name: 'injection-scheduling-v2'
  path: '/modules/production/injection-scheduling'
  factory_id: string | null
  module_id: 'injection-scheduling'
  selected_entity: null
}

export interface AIInternalQuotePageContext {
  route_name: 'internal-quote-desk-home'
  path: '/modules/sales-business/internal-quote-desk'
  factory_id: string | null
  module_id: 'internal-quote'
  selected_entity: null
}

export type AIPageContext = AIInjectionSchedulingPageContext | AIInternalQuotePageContext

export type AIMessageRole = 'user' | 'assistant'

export interface AIConversationMessage {
  id: string
  role: AIMessageRole
  text: string
  status: 'complete' | 'streaming' | 'truncated' | 'error' | 'cancelled'
  createdAt: string
}

export interface AIFailure {
  code: string
  message: string
  retryable: boolean
  retryAfterSeconds?: number
}

export interface AIStreamEnvelope {
  schema_version: '1'
  request_id: string
  sequence: number
  type: string
  timestamp: string
  payload: Record<string, unknown>
}

export interface AIToolActivityItem {
  id: string
  label: string
  status: 'running' | 'complete' | 'error'
}

export interface AIEntityLink {
  label: string
  route: string
  query?: Record<string, string>
}

export interface AISourceSummary {
  id: string
  level: 'FORMAL' | 'MODULE_KNOWLEDGE' | 'USER_PROVIDED' | 'MODEL_INFERENCE' | 'UNKNOWN'
  label: string
  factoryId?: string
  updatedAt?: string
  links: AIEntityLink[]
}

export interface AIBusinessResult {
  id: string
  kind: 'generic' | 'plan_context' | 'backlog' | 'internal_quote_list'
  title: string
  summary: string
  sourceType: string
  factoryId?: string
  asOf?: string
  truncated?: boolean
  links: AIEntityLink[]
  planContext?: {
    executionPublished: AIPlanSummary | null
    planningDraft: AIPlanSummary | null
    pollingRevision?: number
  }
  backlog?: {
    total?: number
    returned?: number
    sourceScope?: string
    sourceBusinessLabel?: string
  }
  internalQuote?: {
    total: number
    returned: number
    limit: number
    offset: number
    quotes: AIInternalQuoteSummary[]
  }
}

export interface AIInternalQuoteSummary {
  quoteId: string
  quoteNo: string
  customer: string
  statusCode: string
  statusLabel: string
  currentStageCode: string
  currentStageLabel: string
  versionLabel: string
  updatedAt: string
  navigationTarget: 'collaboration' | 'summary'
}

export interface AIPlanSummary {
  planId?: string
  businessDate?: string
  revision?: number
  taskCount?: number
  runningCount?: number
}

export interface AIChatRequestMessage {
  role: AIMessageRole
  content: Array<{
    type: 'input_text'
    text: string
  }>
}

export type AIAttachmentMediaType = 'image/png' | 'image/jpeg' | 'image/webp'

export interface AIRequestAttachment {
  id: string
  media_type: AIAttachmentMediaType
  data_url: string
}

export interface AICloudProcessingConsent {
  accepted: true
  notice_version: 'aliyun-cn-beijing-v1'
  attachment_ids: string[]
}
