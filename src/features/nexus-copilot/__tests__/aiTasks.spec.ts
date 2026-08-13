import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  listAITasks: vi.fn(),
  getAITask: vi.fn(),
  getAITaskEvents: vi.fn(),
  cancelAITask: vi.fn(),
  resumeAITask: vi.fn(),
}))

vi.mock('@/api/aiTasks', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/api/aiTasks')>(),
  ...apiMocks,
}))

import type { AITaskDetail, AITaskEvent, AITaskSummary } from '@/api/aiTasks'
import TaskControls from '@/features/nexus-copilot/components/TaskControls.vue'
import TaskList from '@/features/nexus-copilot/components/TaskList.vue'
import TaskTimeline from '@/features/nexus-copilot/components/TaskTimeline.vue'
import { useAITasksStore } from '@/features/nexus-copilot/stores/tasks'

const taskId = `aitask-${'a'.repeat(32)}`
const summary: AITaskSummary = {
  id: taskId,
  conversation_id: `aicv-${'b'.repeat(32)}`,
  factory_scope: 'huaxing',
  task_type: 'COMPUTE',
  state: 'RUNNING',
  maximum_risk: 'READ_ONLY',
  primary_skill_id: 'system.module_tutor',
  revision: 3,
  step_count: 1,
  worker_status: 'LEASED',
  created_at: '2026-08-12T08:00:00+08:00',
  updated_at: '2026-08-12T08:01:00+08:00',
  terminal_at: null,
}

const detail: AITaskDetail = {
  ...summary,
  owner_user_id: 'owner',
  input_message_id: null,
  primary_skill_version: '1.0.0',
  primary_skill_hash: 'a'.repeat(64),
  prompt_version: '1.0.0',
  prompt_hash: 'b'.repeat(64),
  runtime_plan: {},
  runtime_plan_hash: 'c'.repeat(64),
  input_hash: 'd'.repeat(64),
  retention_expires_at: null,
  backup_delete_by: null,
  cancellation_requested_at: null,
  resume_requested_at: null,
  failure_code: '',
  lease_expires_at: '2026-08-12T08:02:30+08:00',
  last_heartbeat_at: '2026-08-12T08:01:00+08:00',
  next_attempt_at: null,
  claim_count: 1,
  steps: [{
    id: `aiste-${'e'.repeat(32)}`,
    task_id: taskId,
    ordinal: 1,
    key: 'compute_answer',
    kind: 'COMPUTE',
    label: '生成有界回答',
    state: 'RUNNING',
    tool_name: null,
    tool_version: null,
    arguments_hash: 'f'.repeat(64),
    side_effect_class: 'NONE',
    idempotent: true,
    revision: 2,
    attempt_count: 1,
    max_attempts: 3,
    result_hash: '',
    result_metadata: {},
    created_at: '2026-08-12T08:00:00+08:00',
    updated_at: '2026-08-12T08:01:00+08:00',
    started_at: '2026-08-12T08:01:00+08:00',
    completed_at: null,
    failure_code: '',
  }],
}

const event = (sequence: number, transitionTo: string): AITaskEvent => ({
  id: `aite-${String(sequence).padStart(32, '0')}`,
  task_id: taskId,
  step_id: null,
  sequence,
  event_type: 'STATE_TRANSITION',
  actor_type: 'SYSTEM',
  transition_from: sequence === 1 ? 'CREATED' : 'UNDERSTOOD',
  transition_to: transitionTo,
  reason_code: `TASK_${transitionTo}`,
  evidence: [],
  artifacts: [],
  created_at: '2026-08-12T08:01:00+08:00',
})

const persistedPreviewManifest = {
  schema_version: 'ai-preview-manifest-v1',
  preview_id: 'isrun-task-preview-1',
  preview_type: 'injection_scheduling.run',
  source_revision_hash: 'a'.repeat(64),
  factory_id: 'huaxing',
  input_hash: 'b'.repeat(64),
  assumptions: [{ key: 'plan_status', label: '计划切片', value: 'DRAFT' }],
  evidence_refs: [{
    evidence_id: 'preview:evidence-task-1',
    source_level: 'FORMAL_DOMAIN_SERVICE',
    source_name: 'injection_scheduling.preview_run',
    factory_id: 'huaxing',
    as_of: '2026-08-12T09:00:00+08:00',
    entity_type: 'scheduling_preview_run',
    entity_id: 'isrun-task-preview-1',
    entity_revision: 1,
    content_hash: `sha256:${'c'.repeat(64)}`,
    truncated: false,
    cursor: null,
    access_policy: 'REAUTHORIZE_ON_OPEN',
  }],
  created_by: 'planner-1',
  created_at: '2026-08-12T09:00:00+08:00',
  expires_at: '2026-08-12T09:30:00+08:00',
  status: 'READY',
  deterministic_service: true,
  can_propose_action: true,
  action_capability: 'CREATE_PROPOSAL_ONLY',
  no_write_performed: true,
}

beforeEach(() => {
  setActivePinia(createPinia())
  Object.values(apiMocks).forEach((mock) => mock.mockReset())
})

describe('NIF-08 persistent task recovery', () => {
  it('deduplicates pages and resumes events strictly after the durable cursor', async () => {
    apiMocks.listAITasks
      .mockResolvedValueOnce({ items: [summary], next_cursor: 'next-page' })
      .mockResolvedValueOnce({ items: [summary], next_cursor: null })
    apiMocks.getAITask.mockResolvedValue(detail)
    apiMocks.getAITaskEvents
      .mockResolvedValueOnce({ items: [event(1, 'UNDERSTOOD')], next_after: 1 })
      .mockResolvedValueOnce({ items: [event(2, 'RUNNING')], next_after: 2 })
    const store = useAITasksStore()

    await store.loadList(true, summary.conversation_id)
    await store.loadList(false)
    await store.open(taskId)
    await store.recoverEvents()

    expect(store.items).toHaveLength(1)
    expect(store.events.map((item) => item.sequence)).toEqual([1, 2])
    expect(apiMocks.getAITaskEvents).toHaveBeenLastCalledWith(taskId, 1)
    store.reset()
  })

  it('clears stale task bodies when current authorization no longer returns them', async () => {
    apiMocks.getAITask.mockResolvedValueOnce(detail).mockRejectedValueOnce(new Error('not found'))
    apiMocks.getAITaskEvents.mockResolvedValue({ items: [], next_after: null })
    const store = useAITasksStore()

    await store.open(taskId)
    await expect(store.open(taskId)).rejects.toThrow('任务不可访问')

    expect(store.active).toBeNull()
    expect(store.events).toEqual([])
    store.reset()
  })

  it('coalesces repeated cancel clicks into one durable command', async () => {
    apiMocks.getAITask
      .mockResolvedValueOnce(detail)
      .mockResolvedValue({ ...detail, state: 'CANCELLING', revision: 4 })
    apiMocks.getAITaskEvents.mockResolvedValue({ items: [], next_after: null })
    let release!: (value: AITaskDetail) => void
    apiMocks.cancelAITask.mockReturnValue(new Promise<AITaskDetail>((resolve) => {
      release = resolve
    }))
    const store = useAITasksStore()
    await store.open(taskId)

    const first = store.cancel()
    const repeated = store.cancel()
    expect(apiMocks.cancelAITask).toHaveBeenCalledOnce()
    release({ ...detail, state: 'CANCELLING', revision: 4 })
    await Promise.all([first, repeated])

    expect(store.active?.state).toBe('CANCELLING')
    store.reset()
  })
})

describe('NIF-08 Task UI states', () => {
  it('shows Worker gating, durable timeline, cancellation and terminal controls', async () => {
    const unavailable = mount(TaskList, {
      props: { items: [], activeId: null, loading: false, available: false, hasMore: false },
    })
    expect(unavailable.text()).toContain('任务 Worker 未开放')

    const timeline = mount(TaskTimeline, {
      props: { task: detail, events: [event(1, 'UNDERSTOOD'), event(2, 'RUNNING')] },
    })
    expect(timeline.text()).toContain('尝试 1/3')
    expect(timeline.text()).toContain('#2 UNDERSTOOD → RUNNING')

    const running = mount(TaskControls, { props: { task: detail, loading: false } })
    await running.get('button:nth-of-type(2)').trigger('click')
    expect(running.emitted('cancel')).toHaveLength(1)

    const failed = mount(TaskControls, {
      props: {
        task: { ...detail, state: 'FAILED', worker_status: 'IDLE', failure_code: 'TASK_PROVIDER_RATE_LIMITED' },
        loading: false,
      },
    })
    expect(failed.text()).toContain('恢复')
    expect(failed.text()).toContain('终态：FAILED')
  })

  it('restores a completed derived Artifact download from persisted step metadata', () => {
    const sourceId = `aiart-${'a'.repeat(32)}`
    const resultId = `aiart-${'b'.repeat(32)}`
    const completed: AITaskDetail = {
      ...detail,
      state: 'COMPLETED',
      worker_status: 'IDLE',
      steps: [{
        ...detail.steps[0]!,
        state: 'COMPLETED',
        result_metadata: {
          source_artifact_id: sourceId,
          result_artifact_id: resultId,
          result_file_name: '订单_中译英.xlsx',
        },
      }],
    }

    const timeline = mount(TaskTimeline, {
      props: { task: completed, events: [] },
    })

    expect(timeline.text()).toContain('可恢复派生文件')
    expect(timeline.text()).toContain(`${sourceId} → 派生件 ${resultId}`)
    expect(timeline.get('a').attributes('href')).toContain(`/ai/artifacts/${resultId}/download`)
  })

  it('restores a verified Preview card from persisted Task metadata', () => {
    const completed: AITaskDetail = {
      ...detail,
      state: 'COMPLETED',
      worker_status: 'IDLE',
      steps: [{
        ...detail.steps[0]!,
        state: 'COMPLETED',
        result_metadata: { preview_manifests: [persistedPreviewManifest] },
      }],
    }

    const timeline = mount(TaskTimeline, {
      props: { task: completed, events: [] },
    })

    expect(timeline.get('[data-preview-card]').text()).toContain('Simulation / Preview')
    expect(timeline.get('[data-preview-card]').text()).toContain('已过期')
    expect(timeline.get('[data-preview-card]').text()).toContain('没有执行正式业务写入')
    expect(timeline.get('[data-preview-card]').text()).toContain('不能继续创建有效 Action Proposal')
  })
})
