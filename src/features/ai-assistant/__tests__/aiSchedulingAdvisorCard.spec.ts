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
import type { AIStreamEnvelope } from '../types'

function event(sequence: number, type: string, payload: Record<string, unknown>): AIStreamEnvelope {
  return {
    schema_version: '1',
    request_id: 'scheduling-advisor-card',
    sequence,
    type,
    timestamp: `2026-08-12T00:00:0${sequence}Z`,
    payload,
  }
}

function run(runId = 'isrun-ai-1', alternativeNo = 1) {
  return {
    run_id: runId,
    plan_id: 'draft-plan-1',
    plan_revision: 7,
    rule_revision: 3,
    status: 'SUCCEEDED',
    requested_solver: 'AUTO',
    actual_solver: 'HEURISTIC',
    solver_status: 'HEURISTIC',
    fallback_used: false,
    scenario_group_id: 'scenario-ai-1',
    scenario_name: alternativeNo === 1 ? '交期优先' : '负载均衡',
    alternative_no: alternativeNo,
    horizon_start: '2026-08-12T08:00:00+08:00',
    horizon_end: '2026-08-26T20:00:00+08:00',
    metrics: {
      input_order_count: 20,
      scheduled_count: 16,
      review_count: 2,
      unassigned_count: 2,
      moved_task_count: 0,
      overdue: { before: 6, after: 2, change: -4 },
      mold_changes: { before: 8, after: 5, change: -3 },
      dark_to_light_changes: { before: 2, after: 1, change: -1 },
      load_ratio_min: 0.4,
      load_ratio_max: 0.8,
      load_ratio_average: 0.625,
      solver_elapsed_ms: 120.5,
    },
  }
}

function previewManifest() {
  return {
    schema_version: 'ai-preview-manifest-v1',
    preview_id: 'isrun-ai-preview-1',
    preview_type: 'injection_scheduling.run',
    source_revision_hash: 'a'.repeat(64),
    factory_id: 'huaxing',
    input_hash: 'b'.repeat(64),
    assumptions: [{ key: 'plan_status', label: '计划切片', value: 'DRAFT' }],
    evidence_refs: [{
      evidence_id: 'preview:evidence-0001',
      source_level: 'FORMAL_DOMAIN_SERVICE',
      source_name: 'injection_scheduling.preview_run',
      factory_id: 'huaxing',
      as_of: '2026-08-12T09:00:00+08:00',
      entity_type: 'scheduling_preview_run',
      entity_id: 'isrun-ai-preview-1',
      entity_revision: 1,
      content_hash: `sha256:${'c'.repeat(64)}`,
      truncated: false,
      cursor: null,
      access_policy: 'REAUTHORIZE_ON_OPEN',
    }],
    created_by: 'planner-1',
    created_at: '2099-08-12T09:00:00+08:00',
    expires_at: '2099-08-12T09:30:00+08:00',
    status: 'READY',
    deterministic_service: true,
    can_propose_action: true,
    action_capability: 'CREATE_PROPOSAL_ONLY',
    no_write_performed: true,
  }
}

function previewData() {
  return {
    schema_version: 'ai-scheduling-preview-v1',
    result_type: 'injection_scheduling.preview_run',
    source_type: 'FORMAL',
    risk_level: 'PREVIEW_WITH_AUDIT',
    factory_id: 'huaxing',
    as_of: '2026-08-12T09:00:00+08:00',
    candidate_label: '候选方案，尚未应用',
    applied: false,
    intent_objective: 'DELIVERY_PRIORITY',
    run: run(),
    entity_links: [{
      label: '在正式排产页面查看候选方案',
      route: '/modules/production/injection-scheduling',
      query: { factory: 'huaxing', autoScheduleRun: 'isrun-ai-1' },
    }],
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
    tool_groups: ['injection_scheduling'],
    pilot_access: {
      granted: true,
      status: 'GRANTED',
      read_only: false,
      max_tool_risk_level: 'PREVIEW_WITH_AUDIT',
    },
  }
  return store
}

beforeEach(() => {
  apiMocks.getAICapabilities.mockReset()
  apiMocks.streamAIResponse.mockReset()
})

describe('AI scheduling advisor card', () => {
  it('labels persisted PREVIEW metrics as a candidate even when model text claims apply', async () => {
    const store = usableStore()
    apiMocks.streamAIResponse.mockImplementationOnce(async (options) => {
      options.onEvent(event(1, 'message.delta', { delta: '已经应用并发布。' }))
      options.onEvent(event(2, 'tool.completed', {
        tool_call_id: 'preview-1',
        tool_name: 'injection_scheduling.generate_preview',
        status: 'completed',
        result: {
          ok: true,
          tool_name: 'injection_scheduling.generate_preview',
          data: previewData(),
          error: null,
          metadata: {},
        },
      }))
      options.onEvent(event(3, 'response.completed', {}))
      return event(3, 'response.completed', {})
    })

    await store.sendMessage('生成交期优先候选方案', null)
    const wrapper = mount(AiBusinessResultCard, {
      props: { results: store.businessResults, sources: store.sources },
    })

    expect(store.canUse).toBe(true)
    expect(store.messages.at(-1)?.text).toContain('已经应用并发布')
    expect(wrapper.get('[data-ai-scheduling-preview]').text()).toContain('候选方案，尚未应用')
    expect(wrapper.get('[data-ai-scheduling-preview]').text()).toContain('已安排16')
    expect(wrapper.get('[data-ai-scheduling-preview]').text()).toContain('平均负载62.5%')
    expect(wrapper.get('[data-ai-scheduling-preview]').text()).toContain('此处不会 Apply 或 Publish')
    expect(wrapper.get('[data-ai-scheduling-preview]').text()).not.toContain('已经应用并发布')
  })

  it('shows whether persisted candidates share a comparable snapshot', async () => {
    const store = usableStore()
    apiMocks.streamAIResponse.mockImplementationOnce(async (options) => {
      options.onEvent(event(1, 'tool.completed', {
        tool_call_id: 'compare-1',
        tool_name: 'injection_scheduling.compare_previews',
        status: 'completed',
        result: {
          ok: true,
          tool_name: 'injection_scheduling.compare_previews',
          data: {
            schema_version: 'ai-scheduling-comparison-v1',
            result_type: 'injection_scheduling.preview_comparison',
            source_type: 'FORMAL',
            factory_id: 'huaxing',
            as_of: '2026-08-12T09:05:00+08:00',
            candidate_label: '候选方案，尚未应用',
            comparable_snapshot: false,
            comparison_warning: '候选方案的计划、规则或时间范围不同，指标不可直接横向比较。',
            runs: [run(), { ...run('isrun-ai-2', 2), plan_revision: 8 }],
            scenario_compare: {
              schema_version: 'ai-scenario-compare-v1',
              preview_type: 'injection_scheduling.run',
              preview_ids: ['isrun-ai-preview-1', 'isrun-ai-preview-2'],
              source_revision_hashes: ['a'.repeat(64), 'b'.repeat(64)],
              comparable: false,
              comparison_basis: 'MIXED_SOURCE_REVISION',
              warning: '候选方案的计划、规则或时间范围不同，指标不可直接横向比较。',
              no_write_performed: true,
            },
            entity_links: [],
          },
          error: null,
          metadata: {},
        },
      }))
      options.onEvent(event(2, 'response.completed', {}))
      return event(2, 'response.completed', {})
    })

    await store.sendMessage('比较两个候选方案', null)
    const wrapper = mount(AiBusinessResultCard, {
      props: { results: store.businessResults, sources: store.sources },
    })
    expect(wrapper.text()).toContain('指标不可直接横向比较')
    expect(wrapper.text()).toContain('交期优先')
    expect(wrapper.text()).toContain('负载均衡')
    expect(store.businessResults[0]?.schedulingPreviews?.scenarioCompare?.comparison_basis).toBe('MIXED_SOURCE_REVISION')
  })

  it('renders the verified generic Preview manifest without claiming execution', async () => {
    const store = usableStore()
    const data = previewData()
    Object.assign(data.run, { preview_manifest: previewManifest() })
    apiMocks.streamAIResponse.mockImplementationOnce(async (options) => {
      options.onEvent(event(1, 'tool.completed', {
        tool_call_id: 'preview-manifest',
        tool_name: 'injection_scheduling.generate_preview',
        status: 'completed',
        result: {
          ok: true,
          tool_name: 'injection_scheduling.generate_preview',
          data,
          error: null,
          metadata: {},
        },
      }))
      options.onEvent(event(2, 'response.completed', {}))
      return event(2, 'response.completed', {})
    })

    await store.sendMessage('生成可审计候选方案', null)
    const wrapper = mount(AiBusinessResultCard, {
      props: { results: store.businessResults, sources: store.sources },
    })
    expect(wrapper.get('[data-preview-card]').text()).toContain('可供复核')
    expect(wrapper.get('[data-preview-card]').text()).toContain('没有执行正式业务写入')

    const unsafeStore = usableStore()
    const unsafe = previewData()
    Object.assign(unsafe.run, {
      preview_manifest: { ...previewManifest(), unknown_field: 'blocked' },
    })
    apiMocks.streamAIResponse.mockImplementationOnce(async (options) => {
      options.onEvent(event(1, 'tool.completed', {
        tool_call_id: 'preview-invalid-manifest',
        tool_name: 'injection_scheduling.generate_preview',
        status: 'completed',
        result: { ok: true, tool_name: 'injection_scheduling.generate_preview', data: unsafe, error: null, metadata: {} },
      }))
      options.onEvent(event(2, 'response.completed', {}))
      return event(2, 'response.completed', {})
    })
    await unsafeStore.sendMessage('生成非法候选方案', null)
    expect(unsafeStore.businessResults).toEqual([])
  })

  it('fails closed when a preview result includes an unregistered assignment field', async () => {
    const store = usableStore()
    const unsafe = previewData()
    Object.assign(unsafe, { assignments: [{ machine_id: 'machine-secret' }] })
    apiMocks.streamAIResponse.mockImplementationOnce(async (options) => {
      options.onEvent(event(1, 'tool.completed', {
        tool_call_id: 'preview-unsafe',
        tool_name: 'injection_scheduling.generate_preview',
        status: 'completed',
        result: {
          ok: true,
          tool_name: 'injection_scheduling.generate_preview',
          data: unsafe,
          error: null,
          metadata: {},
        },
      }))
      options.onEvent(event(2, 'response.completed', {}))
      return event(2, 'response.completed', {})
    })

    await store.sendMessage('生成方案', null)
    expect(store.businessResults).toEqual([])
  })
})
