import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  getAICapabilities: vi.fn(),
  streamAIResponse: vi.fn(),
  createAIConversation: vi.fn(),
  deleteAIConversation: vi.fn(),
  getAIConversation: vi.fn(),
  listAIConversations: vi.fn(),
  listAIContextOptions: vi.fn(),
  setAIConversationContext: vi.fn(),
  getAITaskCapabilities: vi.fn(),
}))

vi.mock('@/api/ai', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/api/ai')>(),
  getAICapabilities: apiMocks.getAICapabilities,
  streamAIResponse: apiMocks.streamAIResponse,
}))

vi.mock('@/api/aiConversations', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/api/aiConversations')>(),
  createAIConversation: apiMocks.createAIConversation,
  deleteAIConversation: apiMocks.deleteAIConversation,
  getAIConversation: apiMocks.getAIConversation,
  listAIConversations: apiMocks.listAIConversations,
  listAIContextOptions: apiMocks.listAIContextOptions,
  setAIConversationContext: apiMocks.setAIConversationContext,
}))

vi.mock('@/api/aiTasks', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/api/aiTasks')>(),
  getAITaskCapabilities: apiMocks.getAITaskCapabilities,
}))

import type { AuthMeResponse } from '@/api/auth'
import AiMessageList from '@/features/ai-assistant/AiMessageList.vue'
import AiComposer from '@/features/ai-assistant/AiComposer.vue'
import { router as applicationRouter } from '@/router'
import { useAuthStore } from '@/stores/auth'
import AiWorkbenchView from '../workbench/AiWorkbenchView.vue'

const conversationId = 'aicv-11111111111111111111111111111111'
const listItem = {
  id: conversationId,
  mode: 'PERSISTENT' as const,
  status: 'ACTIVE' as const,
  title: '跨页恢复会话',
  factory_scope: 'huaxing',
  revision: 3,
  created_at: '2026-08-12T08:00:00+08:00',
  updated_at: '2026-08-12T08:02:00+08:00',
  expires_at: null,
  message_count: 2,
  last_message_at: '2026-08-12T08:02:00+08:00',
  pinned_at: null,
  archived_at: null,
  context_binding: {
    factory_scope: 'huaxing',
    module_id: 'injection-scheduling' as const,
    route_name: 'injection-scheduling-v2' as const,
    path: '/modules/production/injection-scheduling' as const,
    context_version: 1,
    selected_entity_type: '',
    selected_entity_id: '',
    selected_entity_revision: null,
    updated_at: '2026-08-12T08:02:00+08:00',
  },
}

const detail = {
  ...listItem,
  messages: [
    {
      id: 'aimsg-22222222222222222222222222222222',
      conversation_id: conversationId,
      role: 'USER' as const,
      kind: 'TEXT' as const,
      text: '恢复后的问题',
      authority: 'CONVERSATIONAL_ONLY' as const,
      requires_tool_refresh: true as const,
      persisted: true,
      truncated: false,
      skill_id: '',
      skill_version: '',
      skill_hash: '',
      prompt_version: '',
      prompt_hash: '',
      provider_profile: '',
      provider_model_alias: '',
      usage: {},
      evidence: [{
        evidence_id: 'ev:1234567890abcdef',
        source_level: 'FORMAL_DOMAIN_SERVICE',
        source_name: 'scheduling.plan_context',
        factory_id: 'huaxing',
        as_of: '2026-08-12T08:01:00+08:00',
        content_hash: 'a'.repeat(64),
        truncated: false,
        access_policy: 'REAUTHORIZE_ON_OPEN',
      }],
      created_at: '2026-08-12T08:01:00+08:00',
      expires_at: '2026-09-11T08:01:00+08:00',
    },
  ],
  summary: {
    id: 'aisum-33333333333333333333333333333333',
    kind: 'SAFE_STAGE_SUMMARY' as const,
    text: '已安全归纳用户目标。',
    authority: 'CONVERSATIONAL_ONLY' as const,
    requires_tool_refresh: true as const,
    source_message_count: 1,
    prompt_version: '1.1.0',
    prompt_hash: 'b'.repeat(64),
    created_at: '2026-08-12T08:02:00+08:00',
    expires_at: '2026-09-11T08:02:00+08:00',
  },
  next_message_cursor: null,
}

function capabilities() {
  return {
    enabled: true,
    available: true,
    provider: 'test',
    model: 'test',
    streaming: true,
    vision_enabled: false,
    conversation_persistence: true,
    rich_message_renderer_enabled: true,
    presentation_blocks_enabled: true,
    workbench_v2_enabled: true,
    conversation_context_enabled: true,
    feedback_enabled: true,
    tool_groups: ['module_help'],
    pilot_access: { granted: true, status: 'GRANTED' as const, read_only: true },
  }
}

async function mountWorkbench(path = `/workbench/ai?conversation=${conversationId}`) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/workbench/ai', name: 'ai-workbench', component: AiWorkbenchView },
    ],
  })
  await router.push(path)
  await router.isReady()
  const auth = useAuthStore(pinia)
  auth.currentUser = { force_password_change: false } as AuthMeResponse
  auth.isAuthenticated = true
  auth.hasLoadedSession = true
  auth.sessionVersion = 1
  const wrapper = mount(AiWorkbenchView, {
    global: { plugins: [pinia, router] },
  })
  await flushPromises()
  return { wrapper, pinia, router, auth }
}

beforeEach(() => {
  Object.values(apiMocks).forEach((mock) => mock.mockReset())
  apiMocks.getAICapabilities.mockResolvedValue(capabilities())
  apiMocks.getAITaskCapabilities.mockResolvedValue({
    contract_version: '1',
    available: false,
    worker_enabled: false,
  })
  apiMocks.listAIConversations.mockResolvedValue({ items: [listItem], next_cursor: null })
  apiMocks.listAIContextOptions.mockResolvedValue([{
    factory_scope: 'huaxing',
    module_id: 'injection-scheduling',
    route_name: 'injection-scheduling-v2',
    path: '/modules/production/injection-scheduling',
    display_label: '注塑排产',
    tool_groups: ['identity', 'injection_scheduling'],
    maximum_risk: 'PREVIEW_WITH_AUDIT',
  }])
  apiMocks.getAIConversation.mockResolvedValue(detail)
  vi.stubGlobal('matchMedia', vi.fn(() => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })))
  Object.defineProperty(HTMLElement.prototype, 'scrollTo', {
    configurable: true,
    value: vi.fn(),
  })
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('NIF-06 AI Workbench', () => {
  it('registers an authenticated full-page route', () => {
    const resolved = applicationRouter.resolve('/workbench/ai')
    expect(resolved.name).toBe('ai-workbench')
    expect(resolved.meta.requiresAuth).toBe(true)
    expect(resolved.meta.fullPage).toBe(true)
  })

  it('restores a persistent conversation from the URL and shows safe summary and reauthorized evidence', async () => {
    const { wrapper, router } = await mountWorkbench()

    expect(apiMocks.getAIConversation).toHaveBeenCalledWith(conversationId)
    expect(router.currentRoute.value.query.conversation).toBe(conversationId)
    expect(wrapper.text()).toContain('跨页恢复会话')
    expect(wrapper.text()).toContain('恢复后的问题')
    expect(wrapper.get('[data-safe-stage-summary]').text()).toContain('安全阶段摘要（非权威）')
    expect(wrapper.text()).toContain('scheduling.plan_context')
    expect(wrapper.text()).toContain('每次打开都按当前权限重新验证')
    expect(wrapper.findComponent(AiMessageList).props()).toMatchObject({
      feedbackEnabled: true,
      factoryId: 'huaxing',
    })
    wrapper.unmount()
  })

  it('clears in-memory conversation state when the authenticated session changes', async () => {
    const { wrapper, auth } = await mountWorkbench()
    expect(wrapper.text()).toContain('恢复后的问题')

    apiMocks.listAIConversations.mockResolvedValue({ items: [], next_cursor: null })
    apiMocks.getAIConversation.mockRejectedValueOnce(new Error('not found'))
    auth.sessionVersion += 1
    await flushPromises()

    expect(wrapper.text()).not.toContain('恢复后的问题')
    expect(wrapper.text()).toContain('会话不可访问')
    wrapper.unmount()
  })

  it('continues from Workbench with the persisted business context instead of null', async () => {
    apiMocks.streamAIResponse.mockResolvedValue({
      type: 'response.completed',
      payload: {},
    })
    const { wrapper } = await mountWorkbench()

    wrapper.findComponent(AiComposer).vm.$emit('send', '继续查看待排订单')
    await flushPromises()

    expect(apiMocks.streamAIResponse).toHaveBeenCalledWith(expect.objectContaining({
      conversationId,
      pageContext: {
        route_name: 'injection-scheduling-v2',
        path: '/modules/production/injection-scheduling',
        factory_id: 'huaxing',
        module_id: 'injection-scheduling',
        selected_entity: null,
      },
    }))
    wrapper.unmount()
  })
})
