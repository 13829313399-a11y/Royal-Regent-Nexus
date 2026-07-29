import { describe, expect, it, vi } from 'vitest'
import {
  createHttpInjectionSchedulingRepository,
  injectionSchedulingEndpoints,
  type InjectionSchedulingHttpClient,
} from '@/api/injectionScheduling'
import { cloneSchedulingSnapshot } from '@/data/injectionSchedulingMock'

function clientWith(overrides: Partial<InjectionSchedulingHttpClient>) {
  return {
    get: vi.fn(),
    post: vi.fn(),
    ...overrides,
  } as InjectionSchedulingHttpClient
}

describe('injection scheduling HTTP repository', () => {
  it('loads the factory snapshot and maps a 404 to an explicit empty result', async () => {
    const snapshot = cloneSchedulingSnapshot('huaxing')!
    const get = vi.fn()
      .mockResolvedValueOnce({ data: { snapshot } })
      .mockRejectedValueOnce({ response: { status: 404 } })
    const repository = createHttpInjectionSchedulingRepository(clientWith({ get }))

    await expect(repository.loadSnapshot('huaxing')).resolves.toEqual(snapshot)
    expect(get).toHaveBeenCalledWith(
      injectionSchedulingEndpoints.snapshot,
      { params: { factory_id: 'huaxing' } },
    )
    await expect(repository.loadSnapshot('huakang-b')).resolves.toBeNull()
  })

  it('loads only the published snapshot for production big-screen mode', async () => {
    const snapshot = cloneSchedulingSnapshot('huaxing')!
    snapshot.plan.status = 'published'
    const get = vi.fn()
      .mockResolvedValueOnce({ data: { snapshot } })
      .mockRejectedValueOnce({ response: { status: 404 } })
    const repository = createHttpInjectionSchedulingRepository(clientWith({ get }))

    await expect(repository.loadPublishedSnapshot('huaxing')).resolves.toEqual(snapshot)
    expect(get).toHaveBeenNthCalledWith(
      1,
      injectionSchedulingEndpoints.publishedSnapshot,
      { params: { factory_id: 'huaxing' } },
    )
    await expect(repository.loadPublishedSnapshot('huakang-b')).resolves.toBeNull()
  })

  it('maps move, draft and publish payloads to the backend snake-case contract', async () => {
    const snapshot = cloneSchedulingSnapshot('huaxing')!
    const post = vi.fn()
      .mockResolvedValueOnce({
        data: {
          allowed: true,
          reasons: ['通过'],
          affected_task_count: 2,
        },
      })
      .mockResolvedValueOnce({ data: { revision: 4, saved_at: '2026-07-28T10:00:00+08:00' } })
      .mockResolvedValueOnce({ data: { version: '20260728.1', published_at: '2026-07-28T10:01:00+08:00' } })
    const repository = createHttpInjectionSchedulingRepository(clientWith({ post }))

    await expect(repository.validateMove({
      factoryId: 'huaxing',
      revision: 3,
      taskId: 'task-1',
      sourceMachineId: 'machine-1',
      targetMachineId: 'machine-2',
      targetIndex: 1,
    })).resolves.toMatchObject({ allowed: true, affectedTaskCount: 2 })
    await expect(repository.saveDraft({
      factoryId: 'huaxing',
      revision: 3,
      snapshot,
      reason: '人工调整',
    })).resolves.toEqual({ revision: 4, savedAt: '2026-07-28T10:00:00+08:00' })
    await expect(repository.publishVersion({
      factoryId: 'huaxing',
      revision: 4,
      reason: '发布排程',
    })).resolves.toEqual({ version: '20260728.1', publishedAt: '2026-07-28T10:01:00+08:00' })

    expect(post).toHaveBeenNthCalledWith(
      1,
      injectionSchedulingEndpoints.validateMove,
      expect.objectContaining({
        factory_id: 'huaxing',
        source_machine_id: 'machine-1',
        target_machine_id: 'machine-2',
      }),
    )
    expect(post).toHaveBeenNthCalledWith(
      2,
      injectionSchedulingEndpoints.saveDraft,
      expect.objectContaining({ factory_id: 'huaxing', revision: 3, reason: '人工调整' }),
    )
  })

  it('previews and confirms an xlsx import without embedding the file as JSON', async () => {
    const snapshot = cloneSchedulingSnapshot('huakang-b')!
    const post = vi.fn()
      .mockResolvedValueOnce({
        data: {
          batch_id: 'batch-1',
          factory_id: 'huakang-b',
          source_file_name: 'plan.xlsx',
          source_sha256: 'abc',
          business_date: '2026-07-28',
          parser_version: 'v1',
          preview_revision: 1,
          status: 'preview',
          summary: {
            template: 'huakang-b',
            machineCount: 1,
            moldCount: 1,
            orderCount: 1,
            taskCount: 1,
            currentTaskCount: 1,
            blockerCount: 0,
            warningCount: 0,
            canConfirm: true,
          },
          issues: [],
          created_at: '2026-07-28T10:00:00+08:00',
        },
      })
      .mockResolvedValueOnce({ data: { snapshot } })
    const repository = createHttpInjectionSchedulingRepository(clientWith({ post }))
    const file = new File(['xlsx'], 'plan.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })

    const preview = await repository.previewImport('huakang-b', '2026-07-28', file)
    expect(preview.batch_id).toBe('batch-1')
    const firstPayload = vi.mocked(post).mock.calls[0]?.[1]
    expect(firstPayload).toBeInstanceOf(FormData)
    expect((firstPayload as FormData).get('factory_id')).toBe('huakang-b')
    expect((firstPayload as FormData).get('file')).toBe(file)

    await expect(repository.confirmImport('batch-1', {
      factoryId: 'huakang-b',
      previewRevision: 1,
      reason: '确认导入',
    })).resolves.toEqual(snapshot)
    expect(post).toHaveBeenNthCalledWith(
      2,
      injectionSchedulingEndpoints.importConfirm('batch-1'),
      {
        factory_id: 'huakang-b',
        preview_revision: 1,
        reason: '确认导入',
      },
      { timeout: 120_000 },
    )
  })
})
