import { beforeEach, describe, expect, it, vi } from 'vitest'

const { get, post } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))

vi.mock('@/lib/http', () => ({
  http: { get, post },
}))

import { injectionSchedulingApi } from '../api'
import type { ImportBatch, SchedulingWorkbench } from '../types'

describe('injectionSchedulingApi fixed-template contract', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('downloads the controlled workbook in factory scope', async () => {
    const workbook = new Blob(['xlsx'])
    get.mockResolvedValueOnce({ data: workbook })

    await expect(injectionSchedulingApi.downloadTemplate('huakang-b')).resolves.toBe(workbook)

    expect(get).toHaveBeenCalledWith(
      '/injection-scheduling/templates/unified-plan',
      { params: { factory_id: 'huakang-b' }, responseType: 'blob' },
    )
  })

  it('previews only as a fixed planned-schedule profile upload', async () => {
    const file = new File(['xlsx'], 'RR-ISP-1.0.xlsx')
    post.mockResolvedValueOnce({ data: { id: 'batch-1' } })

    await injectionSchedulingApi.previewImport('huaxing', file, '2026-08-26')

    expect(post).toHaveBeenCalledWith(
      '/injection-scheduling/imports/preview',
      expect.any(FormData),
      expect.objectContaining({
        headers: expect.objectContaining({ 'Content-Type': 'multipart/form-data' }),
        timeout: 120_000,
      }),
    )
    const body = post.mock.calls[0]![1] as FormData
    expect(body.get('factory_id')).toBe('huaxing')
    expect(body.get('document_kind')).toBe('PLANNED_SCHEDULE')
    expect(body.get('recognition_mode')).toBe('PROFILE')
    expect(body.get('business_date')).toBe('2026-08-26')
    expect(body.get('file')).toBe(file)
  })

  it('confirms the exact preview fingerprint into its existing draft', async () => {
    const batch = {
      id: 'batch-1',
      factory_id: 'huakang-a',
      revision: 4,
      preview_generation: 2,
      action_fingerprint: 'action-sha',
      resolution_digest: 'resolution-sha',
      plan_context: {
        target_draft_plan_id: 'plan-1',
        target_draft_plan_revision: 7,
        reference_published_plan_id: 'plan-published',
      },
    } as ImportBatch
    post.mockResolvedValueOnce({ data: batch })

    await injectionSchedulingApi.confirmImport(batch, '2026-08-26')

    expect(post).toHaveBeenCalledWith(
      '/injection-scheduling/imports/batch-1/confirm',
      expect.objectContaining({
        factory_id: 'huakang-a',
        expected_revision: 4,
        expected_plan_revision: 7,
        confirm_mode: 'merge_draft',
        expected_preview_generation: 2,
        expected_action_fingerprint: 'action-sha',
        expected_resolution_digest: 'resolution-sha',
        target_draft_plan_id: 'plan-1',
        document_kind: 'PLANNED_SCHEDULE',
      }),
    )
  })

  it('requests a preview-only heuristic schedule and respects locks', async () => {
    const workbench = {
      factory_id: 'huaxing',
      plan_id: 'plan-1',
      plan_revision: 5,
      rule_revision: 3,
      jobs: [
        { order_id: 'order-backlog', status: 'UNPLANNED' },
        { order_id: 'order-running', status: 'RUNNING' },
      ],
    } as SchedulingWorkbench
    post.mockResolvedValueOnce({ data: { id: 'run-1' } })

    await injectionSchedulingApi.createScheduleRun(
      workbench,
      '2026-08-26T00:00:00Z',
      '2026-09-05T00:00:00Z',
    )

    expect(post).toHaveBeenCalledWith(
      '/injection-scheduling/auto-schedule/runs',
      expect.objectContaining({
        mode: 'PREVIEW',
        solver: 'HEURISTIC',
        respect_locked_tasks: true,
        order_ids: ['order-backlog'],
      }),
    )
  })

  it('reassigns an imported queue row without inventing a planning window', async () => {
    const workbench = {
      factory_id: 'huaxing',
      plan_revision: 5,
    } as SchedulingWorkbench
    post.mockResolvedValueOnce({ data: workbench })

    await injectionSchedulingApi.reassignQueuedTask(
      workbench,
      { id: 'task-1', task_revision: 2, order_revision: 3 },
      'machine-2',
      4,
    )

    expect(post).toHaveBeenCalledWith(
      '/injection-scheduling/workbench/jobs/bulk-update',
      expect.objectContaining({
        expected_plan_revision: 5,
        changes: [
          expect.objectContaining({ field: 'machine_id', value: 'machine-2' }),
          expect.objectContaining({ field: 'sequence_no', value: 4 }),
        ],
      }),
    )
    expect(JSON.stringify(post.mock.calls[0]![1])).not.toContain('planned_start')
  })
})
