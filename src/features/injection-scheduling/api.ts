import type { AxiosInstance } from 'axios'

import { http } from '@/lib/http'

import type {
  ImportBatch,
  ManualAppendPreview,
  MatchEvaluation,
  ScheduleRun,
  SchedulingWorkbench,
} from './types'

export function requestId(prefix = 'injection') {
  const id = typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`
  return `${prefix}-${id}`.slice(0, 128)
}

export function createInjectionSchedulingApi(client: AxiosInstance = http) {
  return {
    async getWorkbench(factoryId: string) {
      const response = await client.get<SchedulingWorkbench>('/injection-scheduling/workbench', {
        params: { factory_id: factoryId },
      })
      return response.data
    },
    async downloadTemplate(factoryId: string) {
      const response = await client.get<Blob>('/injection-scheduling/templates/unified-plan', {
        params: { factory_id: factoryId },
        responseType: 'blob',
      })
      return response.data
    },
    async previewImport(factoryId: string, file: File, businessDate: string) {
      const form = new FormData()
      form.append('factory_id', factoryId)
      form.append('expected_revision', '0')
      form.append('document_kind', 'PLANNED_SCHEDULE')
      form.append('recognition_mode', 'PROFILE')
      form.append('business_date', businessDate)
      form.append('file', file)
      const response = await client.post<ImportBatch>('/injection-scheduling/imports/preview', form, {
        headers: {
          'Content-Type': 'multipart/form-data',
          'x-request-id': requestId('preview'),
        },
        timeout: 120_000,
      })
      return response.data
    },
    async confirmImport(batch: ImportBatch, businessDate: string) {
      const targetDraftId = String(batch.plan_context.target_draft_plan_id ?? '')
      const targetDraftRevision = Number(batch.plan_context.target_draft_plan_revision ?? 0)
      const response = await client.post<ImportBatch>(`/injection-scheduling/imports/${batch.id}/confirm`, {
        factory_id: batch.factory_id,
        expected_revision: batch.revision,
        expected_plan_revision: targetDraftRevision,
        request_id: requestId('confirm'),
        confirm_mode: targetDraftId ? 'merge_draft' : 'create_draft',
        business_date: businessDate,
        acknowledged_blocking_issue_ids: [],
        expected_action_fingerprint: batch.action_fingerprint,
        action_reasons: {},
        document_kind: 'PLANNED_SCHEDULE',
        expected_preview_generation: batch.preview_generation,
        expected_resolution_digest: batch.resolution_digest,
        confirm_scope: 'ALL_READY',
        selected_row_ids: [],
        target_draft_plan_id: targetDraftId,
        reference_published_plan_id: String(batch.plan_context.reference_published_plan_id ?? ''),
      })
      return response.data
    },
    async createScheduleRun(workbench: SchedulingWorkbench, horizonStart: string, horizonEnd: string) {
      const response = await client.post<ScheduleRun>('/injection-scheduling/auto-schedule/runs', {
        factory_id: workbench.factory_id,
        plan_id: workbench.plan_id,
        expected_plan_revision: workbench.plan_revision,
        rule_revision: workbench.rule_revision,
        mode: 'PREVIEW',
        horizon_start: horizonStart,
        horizon_end: horizonEnd,
        order_ids: workbench.jobs.filter(job => job.status === 'UNPLANNED').map(job => job.order_id),
        respect_locked_tasks: true,
        solver: 'HEURISTIC',
        time_limit_seconds: 10,
        scenario_name: '默认建议',
      })
      return response.data
    },
    async applyScheduleRun(run: ScheduleRun, workbench: SchedulingWorkbench) {
      const response = await client.post(`/injection-scheduling/auto-schedule/runs/${run.id}/apply`, {
        factory_id: workbench.factory_id,
        expected_plan_revision: workbench.plan_revision,
        expected_rule_revision: workbench.rule_revision,
        request_id: requestId('apply'),
      })
      return response.data
    },
    async evaluateOrder(factoryId: string, orderId: string, allowScheduled: boolean) {
      const response = await client.post<MatchEvaluation>('/injection-scheduling/matches/evaluate', {
        factory_id: factoryId,
        order_id: orderId,
        machine_ids: [],
        allow_scheduled: allowScheduled,
      })
      return response.data
    },
    async previewManualAppend(workbench: SchedulingWorkbench, orderId: string, orderRevision: number, machineId: string) {
      const response = await client.post<ManualAppendPreview>(
        `/injection-scheduling/plans/${workbench.plan_id}/manual-append/preview`,
        {
          factory_id: workbench.factory_id,
          order_id: orderId,
          machine_id: machineId,
          expected_plan_revision: workbench.plan_revision,
          expected_order_revision: orderRevision,
          expected_rule_revision: workbench.rule_revision,
        },
      )
      return response.data
    },
    async confirmManualAppend(preview: ManualAppendPreview) {
      const response = await client.post(
        `/injection-scheduling/plans/${preview.plan_id}/manual-append/confirm`,
        {
          factory_id: preview.factory_id,
          order_id: preview.order_id,
          machine_id: preview.machine_id,
          expected_plan_revision: preview.plan_revision,
          expected_order_revision: preview.order_revision,
          expected_rule_revision: preview.rule_revision,
          request_id: requestId('append'),
          expected_input_fingerprint: preview.input_fingerprint,
          override_reason: '',
        },
      )
      return response.data
    },
    async moveTask(workbench: SchedulingWorkbench, job: { id: string; task_revision: number | null; planned_start: string; planned_finish: string }, machineId: string, sequenceNo: number) {
      const response = await client.post(`/injection-scheduling/plans/${workbench.plan_id}/tasks/bulk-move`, {
        factory_id: workbench.factory_id,
        expected_plan_revision: workbench.plan_revision,
        expected_rule_revision: workbench.rule_revision,
        request_id: requestId('move'),
        moves: [{
          task_id: job.id,
          expected_revision: job.task_revision,
          machine_id: machineId,
          sequence_no: sequenceNo,
          planned_start: job.planned_start,
          planned_finish: job.planned_finish,
          override_reason: '',
        }],
      })
      return response.data
    },
    async withdrawToBacklog(workbench: SchedulingWorkbench, job: { id: string; task_revision: number | null }) {
      const response = await client.post(`/injection-scheduling/tasks/${job.id}/withdraw-to-backlog`, {
        factory_id: workbench.factory_id,
        expected_plan_revision: workbench.plan_revision,
        expected_task_revision: job.task_revision,
        expected_planning_revision: workbench.plan_revision,
        request_id: requestId('withdraw'),
        reason: '排产工作台人工移回待排池',
      })
      return response.data
    },
    async setLocked(workbench: SchedulingWorkbench, job: { id: string; task_revision: number | null; order_revision: number }, locked: boolean) {
      const response = await client.post<SchedulingWorkbench>('/injection-scheduling/workbench/jobs/bulk-update', {
        factory_id: workbench.factory_id,
        expected_plan_revision: workbench.plan_revision,
        request_id: requestId('lock'),
        changes: [{
          job_id: job.id,
          expected_task_revision: job.task_revision,
          expected_order_revision: job.order_revision,
          field: 'locked',
          value: locked,
        }],
      })
      return response.data
    },
    async reassignQueuedTask(workbench: SchedulingWorkbench, job: { id: string; task_revision: number | null; order_revision: number }, machineId: string, sequenceNo: number) {
      const response = await client.post<SchedulingWorkbench>('/injection-scheduling/workbench/jobs/bulk-update', {
        factory_id: workbench.factory_id,
        expected_plan_revision: workbench.plan_revision,
        request_id: requestId('reassign'),
        changes: [
          {
            job_id: job.id,
            expected_task_revision: job.task_revision,
            expected_order_revision: job.order_revision,
            field: 'machine_id',
            value: machineId,
          },
          {
            job_id: job.id,
            expected_task_revision: job.task_revision,
            expected_order_revision: job.order_revision,
            field: 'sequence_no',
            value: sequenceNo,
          },
        ],
      })
      return response.data
    },
    async publishPlan(workbench: SchedulingWorkbench) {
      const response = await client.post(`/injection-scheduling/plans/${workbench.plan_id}/publish`, {
        factory_id: workbench.factory_id,
        expected_revision: workbench.plan_revision,
        request_id: requestId('publish'),
      })
      return response.data
    },
  }
}

export const injectionSchedulingApi = createInjectionSchedulingApi()
