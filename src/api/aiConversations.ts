import { http } from '@/lib/http'
import type { AIPageContext } from '@/features/ai-assistant/types'

export type AIConversationMode = 'PERSISTENT' | 'TEMPORARY'
export type AIConversationStatus = 'ACTIVE' | 'DELETION_PENDING' | 'DELETED' | 'EXPIRED'

export interface AIConversationListItem {
  id: string
  mode: AIConversationMode
  status: AIConversationStatus
  title: string
  factory_scope: string
  revision: number
  created_at: string
  updated_at: string
  expires_at: string | null
  message_count: number
  last_message_at: string | null
  pinned_at: string | null
  archived_at: string | null
  context_binding: AIConversationContextBinding | null
}

export interface AIConversationContextBinding {
  factory_scope: string
  module_id: AIPageContext['module_id']
  route_name: AIPageContext['route_name']
  path: AIPageContext['path']
  context_version: number
  selected_entity_type: string
  selected_entity_id: string
  selected_entity_revision: number | null
  updated_at: string
}

export interface AIContextOption {
  factory_scope: string
  module_id: AIPageContext['module_id']
  route_name: AIPageContext['route_name']
  path: AIPageContext['path']
  display_label: string
  tool_groups: string[]
  maximum_risk: 'PREVIEW_WITH_AUDIT'
}

export interface AIConversationMessage {
  id: string
  conversation_id: string
  role: 'USER' | 'ASSISTANT'
  kind: 'TEXT' | 'SAFE_STAGE_SUMMARY'
  text: string
  authority: 'CONVERSATIONAL_ONLY'
  requires_tool_refresh: true
  persisted: boolean
  truncated: boolean
  skill_id: string
  skill_version: string
  skill_hash: string
  prompt_version: string
  prompt_hash: string
  provider_profile: string
  provider_model_alias: string
  usage: Readonly<Record<string, number>>
  evidence: readonly Readonly<Record<string, unknown>>[]
  created_at: string
  expires_at: string | null
}

export interface AIConversationSummary {
  id: string
  kind: 'SAFE_STAGE_SUMMARY'
  text: string
  authority: 'CONVERSATIONAL_ONLY'
  requires_tool_refresh: true
  source_message_count: number
  prompt_version: string
  prompt_hash: string
  created_at: string
  expires_at: string
}

export interface AIConversationDetail extends AIConversationListItem {
  messages: AIConversationMessage[]
  summary: AIConversationSummary | null
  next_message_cursor: string | null
}

export interface AIConversationListPage {
  items: AIConversationListItem[]
  next_cursor: string | null
}

const CONVERSATION_ID = /^aicv-[0-9a-f]{32}$/
const MESSAGE_ID = /^aimsg-[0-9a-f]{32}$/
const FACTORY_IDS = new Set([
  'huakang-a',
  'huakang-b',
  'huakang-c',
  'huakang-d',
  'huadeng',
  'huaxing',
])

export function isAIConversationId(value: unknown): value is string {
  return typeof value === 'string' && CONVERSATION_ID.test(value)
}

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('AI conversation response is not an object')
  }
  return value as Record<string, unknown>
}

function closed(source: Record<string, unknown>, allowed: readonly string[]) {
  const allowedKeys = new Set(allowed)
  if (Object.keys(source).some((key) => !allowedKeys.has(key))) {
    throw new Error('AI conversation response contains an unknown field')
  }
}

function text(source: Record<string, unknown>, key: string, max: number) {
  const value = source[key]
  if (typeof value !== 'string' || value.length > max) {
    throw new Error(`AI conversation ${key} is invalid`)
  }
  return value
}

function integer(source: Record<string, unknown>, key: string, minimum = 0) {
  const value = source[key]
  if (!Number.isInteger(value) || (value as number) < minimum) {
    throw new Error(`AI conversation ${key} is invalid`)
  }
  return value as number
}

function timestamp(source: Record<string, unknown>, key: string, nullable: true): string | null
function timestamp(source: Record<string, unknown>, key: string, nullable?: false): string
function timestamp(source: Record<string, unknown>, key: string, nullable = false): string | null {
  const value = source[key]
  if (nullable && value === null) return null
  if (typeof value !== 'string' || !value || !Number.isFinite(Date.parse(value))) {
    throw new Error(`AI conversation ${key} is invalid`)
  }
  return value
}

function optionalTimestamp(source: Record<string, unknown>, key: string) {
  return source[key] === undefined ? null : timestamp(source, key, true)
}

const CONTEXT_ROUTES = new Set([
  'injection-scheduling-v2', 'internal-quote-desk-home', 'molding-sample',
  'carton-procurement', 'raw-material-management', 'customer-order-center', 'ai-workbench',
])
const CONTEXT_MODULES = new Set([
  'injection-scheduling', 'internal-quote', 'molding-sample', 'carton-procurement',
  'raw-material', 'customer-order', 'ai-workbench',
])
const CONTEXT_PATHS = new Set([
  '/modules/production/injection-scheduling',
  '/modules/sales-business/internal-quote-desk',
  '/modules/molding-sample',
  '/modules/pmc-warehouse/carton-procurement',
  '/modules/pmc-warehouse/raw-material-management',
  '/modules/sales-business/po-schedule-intake',
  '/workbench/ai',
])

function contextIdentity(source: Record<string, unknown>) {
  const factoryScope = text(source, 'factory_scope', 64)
  const moduleId = text(source, 'module_id', 64)
  const routeName = text(source, 'route_name', 96)
  const path = text(source, 'path', 255)
  if (!FACTORY_IDS.has(factoryScope)
    || !CONTEXT_MODULES.has(moduleId)
    || !CONTEXT_ROUTES.has(routeName)
    || !CONTEXT_PATHS.has(path)) {
    throw new Error('AI conversation context is invalid')
  }
  return {
    factory_scope: factoryScope,
    module_id: moduleId as AIPageContext['module_id'],
    route_name: routeName as AIPageContext['route_name'],
    path: path as AIPageContext['path'],
  }
}

function parseContextBinding(value: unknown): AIConversationContextBinding {
  const source = record(value)
  closed(source, [
    'factory_scope', 'module_id', 'route_name', 'path', 'context_version',
    'selected_entity_type', 'selected_entity_id', 'selected_entity_revision', 'updated_at',
  ])
  const revision = source.selected_entity_revision
  if (revision !== null && (!Number.isInteger(revision) || (revision as number) < 1)) {
    throw new Error('AI conversation selected entity revision is invalid')
  }
  return {
    ...contextIdentity(source),
    context_version: integer(source, 'context_version', 1),
    selected_entity_type: text(source, 'selected_entity_type', 64),
    selected_entity_id: text(source, 'selected_entity_id', 96),
    selected_entity_revision: revision as number | null,
    updated_at: timestamp(source, 'updated_at'),
  }
}

function parseContextOption(value: unknown): AIContextOption {
  const source = record(value)
  closed(source, [
    'factory_scope', 'module_id', 'route_name', 'path', 'display_label',
    'tool_groups', 'maximum_risk',
  ])
  if (!Array.isArray(source.tool_groups)
    || source.tool_groups.some((item) => typeof item !== 'string')
    || source.maximum_risk !== 'PREVIEW_WITH_AUDIT') {
    throw new Error('AI context option capability is invalid')
  }
  return {
    ...contextIdentity(source),
    display_label: text(source, 'display_label', 64),
    tool_groups: [...source.tool_groups] as string[],
    maximum_risk: 'PREVIEW_WITH_AUDIT',
  }
}

function parseListItem(value: unknown): AIConversationListItem {
  const source = record(value)
  closed(source, [
    'id', 'mode', 'status', 'title', 'factory_scope', 'revision', 'created_at',
    'updated_at', 'expires_at', 'message_count', 'last_message_at', 'pinned_at',
    'archived_at', 'context_binding',
  ])
  const id = text(source, 'id', 64)
  const mode = source.mode
  const status = source.status
  const factoryScope = text(source, 'factory_scope', 64)
  if (!CONVERSATION_ID.test(id)) throw new Error('AI conversation id is invalid')
  if (mode !== 'PERSISTENT' && mode !== 'TEMPORARY') {
    throw new Error('AI conversation mode is invalid')
  }
  if (!['ACTIVE', 'DELETION_PENDING', 'DELETED', 'EXPIRED'].includes(String(status))) {
    throw new Error('AI conversation status is invalid')
  }
  if (!FACTORY_IDS.has(factoryScope)) throw new Error('AI conversation factory is invalid')
  return {
    id,
    mode,
    status: status as AIConversationStatus,
    title: text(source, 'title', 160),
    factory_scope: factoryScope,
    revision: integer(source, 'revision', 1),
    created_at: timestamp(source, 'created_at'),
    updated_at: timestamp(source, 'updated_at'),
    expires_at: timestamp(source, 'expires_at', true),
    message_count: integer(source, 'message_count'),
    last_message_at: timestamp(source, 'last_message_at', true),
    pinned_at: optionalTimestamp(source, 'pinned_at'),
    archived_at: optionalTimestamp(source, 'archived_at'),
    context_binding: source.context_binding == null
      ? null
      : parseContextBinding(source.context_binding),
  }
}

function parseMessage(value: unknown): AIConversationMessage {
  const source = record(value)
  closed(source, [
    'id', 'conversation_id', 'role', 'kind', 'text', 'authority',
    'requires_tool_refresh', 'persisted', 'truncated', 'skill_id', 'skill_version',
    'skill_hash', 'prompt_version', 'prompt_hash', 'provider_profile',
    'provider_model_alias', 'usage', 'evidence', 'created_at', 'expires_at',
  ])
  const id = text(source, 'id', 64)
  const conversationId = text(source, 'conversation_id', 64)
  if (!MESSAGE_ID.test(id) || !CONVERSATION_ID.test(conversationId)) {
    throw new Error('AI conversation message identity is invalid')
  }
  if (source.role !== 'USER' && source.role !== 'ASSISTANT') {
    throw new Error('AI conversation message role is invalid')
  }
  if (source.kind !== 'TEXT' && source.kind !== 'SAFE_STAGE_SUMMARY') {
    throw new Error('AI conversation message kind is invalid')
  }
  if (source.authority !== 'CONVERSATIONAL_ONLY' || source.requires_tool_refresh !== true) {
    throw new Error('AI conversation message authority is invalid')
  }
  const usageSource = record(source.usage)
  const usage = Object.fromEntries(Object.entries(usageSource).map(([key, item]) => {
    if (!Number.isInteger(item) || (item as number) < 0) {
      throw new Error('AI conversation usage is invalid')
    }
    return [key, item as number]
  }))
  if (!Array.isArray(source.evidence)) throw new Error('AI conversation evidence is invalid')
  return {
    id,
    conversation_id: conversationId,
    role: source.role,
    kind: source.kind,
    text: text(source, 'text', 8_000),
    authority: 'CONVERSATIONAL_ONLY',
    requires_tool_refresh: true,
    persisted: source.persisted === true,
    truncated: source.truncated === true,
    skill_id: text(source, 'skill_id', 128),
    skill_version: text(source, 'skill_version', 64),
    skill_hash: text(source, 'skill_hash', 64),
    prompt_version: text(source, 'prompt_version', 128),
    prompt_hash: text(source, 'prompt_hash', 64),
    provider_profile: text(source, 'provider_profile', 128),
    provider_model_alias: text(source, 'provider_model_alias', 128),
    usage,
    evidence: source.evidence.map((item) => record(item)),
    created_at: timestamp(source, 'created_at'),
    expires_at: timestamp(source, 'expires_at', true),
  }
}

function parseSummary(value: unknown): AIConversationSummary {
  const source = record(value)
  closed(source, [
    'id', 'kind', 'text', 'authority', 'requires_tool_refresh',
    'source_message_count', 'prompt_version', 'prompt_hash', 'created_at', 'expires_at',
  ])
  const id = text(source, 'id', 64)
  if (!/^aisum-[0-9a-f]{32}$/.test(id)
    || source.kind !== 'SAFE_STAGE_SUMMARY'
    || source.authority !== 'CONVERSATIONAL_ONLY'
    || source.requires_tool_refresh !== true) {
    throw new Error('AI conversation summary is invalid')
  }
  return {
    id,
    kind: 'SAFE_STAGE_SUMMARY',
    text: text(source, 'text', 4_000),
    authority: 'CONVERSATIONAL_ONLY',
    requires_tool_refresh: true,
    source_message_count: integer(source, 'source_message_count'),
    prompt_version: text(source, 'prompt_version', 128),
    prompt_hash: text(source, 'prompt_hash', 64),
    created_at: timestamp(source, 'created_at'),
    expires_at: timestamp(source, 'expires_at'),
  }
}

export function parseAIConversationListPage(value: unknown): AIConversationListPage {
  const source = record(value)
  closed(source, ['items', 'next_cursor'])
  if (!Array.isArray(source.items)) throw new Error('AI conversation list is invalid')
  const nextCursor = source.next_cursor
  if (nextCursor !== null && (typeof nextCursor !== 'string' || !nextCursor || nextCursor.length > 512)) {
    throw new Error('AI conversation cursor is invalid')
  }
  return {
    items: source.items.map(parseListItem),
    next_cursor: nextCursor,
  }
}

export function parseAIConversationDetail(value: unknown): AIConversationDetail {
  const source = record(value)
  const listFields = [
    'id', 'mode', 'status', 'title', 'factory_scope', 'revision', 'created_at',
    'updated_at', 'expires_at', 'message_count', 'last_message_at', 'pinned_at',
    'archived_at', 'context_binding',
  ] as const
  closed(source, [...listFields, 'messages', 'summary', 'next_message_cursor'])
  const listValue = Object.fromEntries(listFields.map((key) => [key, source[key]]))
  if (!Array.isArray(source.messages)) throw new Error('AI conversation messages are invalid')
  const nextCursor = source.next_message_cursor
  if (nextCursor !== null && (typeof nextCursor !== 'string' || !nextCursor || nextCursor.length > 512)) {
    throw new Error('AI conversation message cursor is invalid')
  }
  return {
    ...parseListItem(listValue),
    messages: source.messages.map(parseMessage),
    summary: source.summary === null ? null : parseSummary(source.summary),
    next_message_cursor: nextCursor,
  }
}

export async function createAIConversation(input: {
  mode: AIConversationMode
  factoryScope: string
  title?: string
}) {
  const response = await http.post('/ai/conversations', {
    mode: input.mode,
    factory_scope: input.factoryScope,
    title: input.title ?? '',
  })
  return parseListItem(response.data)
}

export async function listAIConversations(cursor?: string, limit = 20) {
  const response = await http.get('/ai/conversations', {
    params: { limit, ...(cursor ? { cursor } : {}) },
  })
  return parseAIConversationListPage(response.data)
}

export async function getAIConversation(
  conversationId: string,
  options: { messageCursor?: string; messageLimit?: number } = {},
) {
  const response = await http.get(`/ai/conversations/${encodeURIComponent(conversationId)}`, {
    params: {
      message_limit: options.messageLimit ?? 50,
      ...(options.messageCursor ? { message_cursor: options.messageCursor } : {}),
    },
  })
  return parseAIConversationDetail(response.data)
}

export async function appendAIConversationMessage(input: {
  conversationId: string
  text: string
  idempotencyKey: string
  expectedRevision?: number
}) {
  const response = await http.post(
    `/ai/conversations/${encodeURIComponent(input.conversationId)}/messages`,
    {
      text: input.text,
      idempotency_key: input.idempotencyKey,
      ...(input.expectedRevision !== undefined
        ? { expected_revision: input.expectedRevision }
        : {}),
    },
  )
  return parseMessage(response.data)
}

export async function deleteAIConversation(conversationId: string) {
  await http.delete(`/ai/conversations/${encodeURIComponent(conversationId)}`)
}

export async function listAIContextOptions(factoryScope: string) {
  const response = await http.get('/ai/context-options', {
    params: { factory_id: factoryScope },
  })
  const source = record(response.data)
  closed(source, ['items'])
  if (!Array.isArray(source.items)) throw new Error('AI context options are invalid')
  return source.items.map(parseContextOption)
}

export async function setAIConversationContext(input: {
  conversationId: string
  pageContext: AIPageContext | null
  expectedRevision?: number
}) {
  const response = await http.patch(
    `/ai/conversations/${encodeURIComponent(input.conversationId)}/context`,
    {
      page_context: input.pageContext,
      ...(input.expectedRevision !== undefined
        ? { expected_revision: input.expectedRevision }
        : {}),
    },
  )
  return response.data === null ? null : parseContextBinding(response.data)
}

export async function updateAIConversation(input: {
  conversationId: string
  title?: string
  pinned?: boolean
  archived?: boolean
  expectedRevision?: number
}) {
  const response = await http.patch(
    `/ai/conversations/${encodeURIComponent(input.conversationId)}`,
    {
      ...(input.title !== undefined ? { title: input.title } : {}),
      ...(input.pinned !== undefined ? { pinned: input.pinned } : {}),
      ...(input.archived !== undefined ? { archived: input.archived } : {}),
      ...(input.expectedRevision !== undefined
        ? { expected_revision: input.expectedRevision }
        : {}),
    },
  )
  return parseListItem(response.data)
}
