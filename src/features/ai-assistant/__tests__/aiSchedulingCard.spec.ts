import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  getAICapabilities: vi.fn(),
  streamAIResponse: vi.fn(),
}))

vi.mock('@/api/ai', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/api/ai')>(),
  getAICapabilities: apiMocks.getAICapabilities,
  streamAIResponse: apiMocks.streamAIResponse,
}))

import AiBusinessResultCard from '../AiBusinessResultCard.vue'
import { useAIAssistantStore } from '../store'
import type { AIChatRequestMessage, AIStreamEnvelope } from '../types'

function event(sequence: number, type: string, payload: Record<string, unknown>): AIStreamEnvelope {
  return {
    schema_version: '1',
    request_id: 'web-card-test',
    sequence,
    type,
    timestamp: `2026-08-11T00:00:0${sequence}Z`,
    payload,
  }
}

function usableStore() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useAIAssistantStore(pinia)
  store.capabilities = {
    enabled: true,
    available: true,
    provider: 'test',
    model: 'test',
    streaming: true,
    vision_enabled: false,
    conversation_persistence: false,
    tool_groups: ['scheduling'],
    pilot_access: { granted: true, status: 'GRANTED', read_only: true },
  }
  return store
}

beforeEach(() => {
  apiMocks.getAICapabilities.mockReset()
  apiMocks.streamAIResponse.mockReset()
})

describe('AI structured business cards', () => {
  it('submits only the newest bounded in-memory history', async () => {
    const store = usableStore()
    apiMocks.streamAIResponse.mockImplementation(async (options) => {
      options.onEvent(event(1, 'message.delta', { delta: '完成' }))
      options.onEvent(event(2, 'response.completed', {}))
      return event(2, 'response.completed', {})
    })

    for (let index = 0; index < 7; index += 1) {
      await store.sendMessage(`${index}:${'问'.repeat(7_000)}`, null)
    }

    const lastOptions = apiMocks.streamAIResponse.mock.calls.at(-1)?.[0]
    const submittedChars = (lastOptions.messages as AIChatRequestMessage[]).reduce((total, message) => (
      total + message.content[0].text.length
    ), 0)
    expect(submittedChars).toBeLessThanOrEqual(40_000)
    expect(lastOptions.messages.at(-1).content[0].text).toMatch(/^6:/)
    expect(store.messages.length).toBeLessThanOrEqual(12)
  })

  it('extracts B4 module help only from tool.completed result.data', async () => {
    const store = usableStore()
    apiMocks.streamAIResponse.mockImplementationOnce(async (options) => {
      options.onEvent(event(1, 'tool.started', {
        tool_call_id: 'module-help-1',
        tool_name: 'knowledge.get_module_help',
        status: 'running',
      }))
      options.onEvent(event(2, 'tool.completed', {
        tool_call_id: 'module-help-1',
        tool_name: 'knowledge.get_module_help',
        status: 'completed',
        result: {
          ok: true,
          tool_name: 'knowledge.get_module_help',
          data: {
            source_type: 'VERSIONED_MODULE_KNOWLEDGE',
            knowledge_id: 'injection-scheduling',
            knowledge_version: '1',
            module_name: '注塑排产页面帮助',
            last_reviewed_at: '2026-08-11',
            reviewed_against_commit: 'test-commit',
            route_names: ['injection-scheduling-v2'],
            business_purpose: '解释注塑排产中枢。',
            authoritative_data_status: '帮助文档不是实时业务数据。',
            required_permissions: ['injection_scheduling:read'],
            normal_workflow: ['确认厂区', '查看计划'],
            status_labels: { PUBLISHED: '执行中', DRAFT: '规划草案' },
            common_errors: ['厂区无权限'],
            prohibited_claims: ['不得把草案称为执行计划'],
            source_files: ['src/features/injection-scheduling-v2/InjectionSchedulingV2View.vue'],
            help_markdown: '先确认厂区，再查看执行计划与规划草案。\n\n**这段内容必须按纯文本显示。**',
          },
          error: null,
          metadata: {},
        },
      }))
      options.onEvent(event(3, 'response.completed', {}))
      return event(3, 'response.completed', {})
    })

    await store.sendMessage('这个页面怎么用？', null)

    expect(store.activities).toHaveLength(1)
    expect(store.activities[0]).toMatchObject({ id: 'module-help-1', status: 'complete' })
    expect(store.businessResults).toHaveLength(1)
    expect(store.businessResults[0]).toMatchObject({
      kind: 'generic',
      sourceType: 'VERSIONED_MODULE_KNOWLEDGE',
      title: '注塑排产页面帮助',
    })
    const wrapper = mount(AiBusinessResultCard, {
      props: { results: store.businessResults, sources: store.sources },
    })
    expect(wrapper.text()).toContain('先确认厂区，再查看执行计划与规划草案。')
    expect(wrapper.text()).toContain('受控页面知识')
    expect(wrapper.text()).toContain('**这段内容必须按纯文本显示。**')
    expect(wrapper.find('strong').exists()).toBe(false)
    expect(store.sources[0]).toMatchObject({
      level: 'MODULE_KNOWLEDGE',
      label: '受控页面知识',
      updatedAt: '2026-08-11',
    })
  })

  it('keeps PUBLISHED execution and DRAFT planning labels fixed despite a contradictory model delta', async () => {
    const store = usableStore()
    apiMocks.streamAIResponse.mockImplementationOnce(async (options) => {
      options.onEvent(event(1, 'tool.started', {
        tool_call_id: 'plan-context-1',
        tool_name: 'injection_scheduling.get_plan_context',
        status: 'running',
      }))
      options.onEvent(event(2, 'message.delta', {
        delta: '模型声称：DRAFT 正在执行。',
      }))
      options.onEvent(event(3, 'tool.completed', {
        tool_call_id: 'plan-context-1',
        tool_name: 'injection_scheduling.get_plan_context',
        status: 'completed',
        result: {
          ok: true,
          tool_name: 'injection_scheduling.get_plan_context',
          data: {
            source_type: 'FORMAL',
            factory_id: 'huaxing',
            as_of: '2026-08-11T09:00:00Z',
            execution_published: {
              plan_id: 'published-1',
              business_date: '2026-08-11',
              revision: 8,
              task_count: 100,
              running_count: 12,
            },
            planning_draft: {
              plan_id: 'draft-1',
              business_date: '2026-08-12',
              revision: 3,
              task_count: 110,
            },
            polling_revision: 123,
            entity_links: [{
              label: '打开注塑排产中枢',
              route: '/modules/production/injection-scheduling',
              query: { factory: 'huaxing' },
            }],
          },
          error: null,
          metadata: {},
        },
      }))
      options.onEvent(event(4, 'response.completed', {}))
      return event(4, 'response.completed', {})
    })

    await store.sendMessage('华兴当前排产是什么？', null)
    expect(store.messages.at(-1)?.text).toContain('DRAFT 正在执行')
    expect(store.activities).toEqual([
      expect.objectContaining({ id: 'plan-context-1', status: 'complete' }),
    ])
    const wrapper = mount(AiBusinessResultCard, {
      props: { results: store.businessResults, sources: store.sources },
    })
    expect(wrapper.get('[data-plan-kind="published"]').text()).toContain('当前执行 PUBLISHED')
    expect(wrapper.get('[data-plan-kind="published"]').text()).toContain('任务 100')
    expect(wrapper.get('[data-plan-kind="draft"]').text()).toContain('规划草案 DRAFT')
    expect(wrapper.get('[data-plan-kind="draft"]').text()).toContain('任务 110')
    expect(wrapper.text()).not.toContain('DRAFT 正在执行')
  })

  it('shows backlog total, returned, truncation and source scope from structured data', async () => {
    const store = usableStore()
    apiMocks.streamAIResponse.mockImplementationOnce(async (options) => {
      options.onEvent(event(1, 'tool.completed', {
        tool_call_id: 'backlog-1',
        tool_name: 'injection_scheduling.get_backlog',
        status: 'completed',
        result: {
          ok: true,
          tool_name: 'injection_scheduling.get_backlog',
          data: {
            source_type: 'FORMAL',
            factory_id: 'huaxing',
            as_of: '2026-08-11T09:00:00Z',
            source_scope: 'PLANNING_DRAFT',
            source_business_label: '规划草案待排池',
            total: 42,
            limit: 20,
            offset: 0,
            returned: 20,
            truncated: true,
            items: [{
              order_id: 'order-1',
              order_no: '000123',
              item_no: 'ITEM-1',
              product_name: '测试产品',
              mold_no: 'M-001',
              priority_code: 'URGENT',
              priority_business_label: '加急',
              delivery_due_date: '2026-08-12',
              order_quantity: 100,
              outstanding_quantity: 80,
              mold_enrichment_status: 'MATCHED',
              mold_enrichment_business_label: '共享资料已补齐',
              source_type: 'DEMAND_ORDER',
            }],
            entity_links: [{
              label: '打开注塑排产中枢',
              route: '/modules/production/injection-scheduling',
              query: { factory: 'huaxing' },
            }],
          },
          error: null,
          metadata: {},
        },
      }))
      options.onEvent(event(2, 'response.completed', {}))
      return event(2, 'response.completed', {})
    })

    await store.sendMessage('有哪些急单没排？', null)
    const wrapper = mount(AiBusinessResultCard, {
      props: { results: store.businessResults, sources: store.sources },
    })
    expect(wrapper.text()).toContain('全部待排42')
    expect(wrapper.text()).toContain('本次返回20')
    expect(wrapper.text()).toContain('规划草案待排池')
    expect(wrapper.text()).not.toContain('PLANNING_DRAFT')
    expect(wrapper.text()).toContain('结果已按安全上限截断')
  })
})
