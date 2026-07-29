import { http } from '@/lib/http'
import type { ProductionFactoryContextId } from '@/data/enterpriseMock'
import type {
  MoveValidation,
  ScheduleMoveRequest,
  SchedulingSnapshot,
} from '@/types/injectionScheduling'

export interface DraftSaveRequest {
  factoryId: ProductionFactoryContextId
  revision: number
  snapshot: SchedulingSnapshot
  reason: string
}

export interface PublishVersionRequest {
  factoryId: ProductionFactoryContextId
  revision: number
  reason: string
}

export interface RollbackVersionRequest {
  factoryId: ProductionFactoryContextId
  revision: number
  version: string
  reason: string
}

export interface InjectionSchedulingImportIssue {
  id: string
  severity: 'blocker' | 'warning'
  code: string
  message: string
  sheet_name: string
  source_row: number
  field: string
  source_value: string
}

export interface InjectionSchedulingImportPreview {
  batch_id: string
  factory_id: ProductionFactoryContextId
  source_file_name: string
  source_sha256: string
  business_date: string
  parser_version: string
  preview_revision: number
  status: string
  summary: {
    template: string
    machineCount: number
    moldCount: number
    orderCount: number
    taskCount: number
    currentTaskCount: number
    blockerCount: number
    warningCount: number
    canConfirm: boolean
  }
  issues: InjectionSchedulingImportIssue[]
  created_at: string
}

export interface InjectionSchedulingHttpClient {
  get<T = unknown>(url: string, config?: unknown): Promise<{ data: T }>
  post<T = unknown>(url: string, data?: unknown, config?: unknown): Promise<{ data: T }>
}

export interface InjectionSchedulingRepository {
  loadSnapshot(factoryId: ProductionFactoryContextId): Promise<SchedulingSnapshot | null>
  validateMove(request: ScheduleMoveRequest): Promise<MoveValidation>
  saveDraft(request: DraftSaveRequest): Promise<{ revision: number; savedAt: string }>
  publishVersion(request: PublishVersionRequest): Promise<{ version: string; publishedAt: string }>
  loadPublishedSnapshot(factoryId: ProductionFactoryContextId): Promise<SchedulingSnapshot | null>
  previewImport(
    factoryId: ProductionFactoryContextId,
    businessDate: string,
    file: File,
  ): Promise<InjectionSchedulingImportPreview>
  confirmImport(
    batchId: string,
    request: { factoryId: ProductionFactoryContextId; previewRevision: number; reason: string },
  ): Promise<SchedulingSnapshot>
  rollbackVersion(request: RollbackVersionRequest): Promise<SchedulingSnapshot>
}

export const injectionSchedulingEndpoints = {
  snapshot: '/injection-scheduling/snapshots/current',
  validateMove: '/injection-scheduling/moves/validate',
  saveDraft: '/injection-scheduling/plans/draft',
  publishVersion: '/injection-scheduling/plans/publish',
  publishedSnapshot: '/injection-scheduling/published/current',
  importPreview: '/injection-scheduling/imports/preview',
  importConfirm: (batchId: string) => `/injection-scheduling/imports/${batchId}/confirm`,
  rollbackVersion: '/injection-scheduling/plans/rollback',
} as const

function isNotFound(error: unknown) {
  return Boolean(
    error
    && typeof error === 'object'
    && 'response' in error
    && (error as { response?: { status?: number } }).response?.status === 404,
  )
}

export function createHttpInjectionSchedulingRepository(
  client: InjectionSchedulingHttpClient = http,
): InjectionSchedulingRepository {
  return {
    async loadSnapshot(factoryId) {
      try {
        const response = await client.get<{ snapshot: SchedulingSnapshot }>(
          injectionSchedulingEndpoints.snapshot,
          { params: { factory_id: factoryId } },
        )
        return response.data.snapshot
      } catch (error) {
        if (isNotFound(error)) return null
        throw error
      }
    },
    async validateMove(request) {
      const response = await client.post<{
        allowed: boolean
        eligibility?: MoveValidation['eligibility']
        reasons: string[]
        affected_task_count: number
      }>(
        injectionSchedulingEndpoints.validateMove,
        {
          factory_id: request.factoryId,
          revision: request.revision,
          task_id: request.taskId,
          backlog_id: request.backlogId,
          source_machine_id: request.sourceMachineId,
          target_machine_id: request.targetMachineId,
          target_index: request.targetIndex,
        },
      )
      return {
        allowed: response.data.allowed,
        eligibility: response.data.eligibility,
        reasons: response.data.reasons,
        affectedTaskCount: response.data.affected_task_count,
      }
    },
    async saveDraft(request) {
      const response = await client.post<{
        revision: number
        saved_at: string
      }>(
        injectionSchedulingEndpoints.saveDraft,
        {
          factory_id: request.factoryId,
          revision: request.revision,
          snapshot: request.snapshot,
          reason: request.reason,
        },
      )
      return { revision: response.data.revision, savedAt: response.data.saved_at }
    },
    async publishVersion(request) {
      const response = await client.post<{
        version: string
        published_at: string
      }>(
        injectionSchedulingEndpoints.publishVersion,
        {
          factory_id: request.factoryId,
          revision: request.revision,
          reason: request.reason,
        },
      )
      return { version: response.data.version, publishedAt: response.data.published_at }
    },
    async loadPublishedSnapshot(factoryId) {
      try {
        const response = await client.get<{ snapshot: SchedulingSnapshot }>(
          injectionSchedulingEndpoints.publishedSnapshot,
          { params: { factory_id: factoryId } },
        )
        return response.data.snapshot
      } catch (error) {
        if (isNotFound(error)) return null
        throw error
      }
    },
    async previewImport(factoryId, businessDate, file) {
      const payload = new FormData()
      payload.append('factory_id', factoryId)
      payload.append('business_date', businessDate)
      payload.append('file', file)
      const response = await client.post<InjectionSchedulingImportPreview>(
        injectionSchedulingEndpoints.importPreview,
        payload,
        {
          headers: { 'Content-Type': 'multipart/form-data' },
          timeout: 120_000,
        },
      )
      return response.data
    },
    async confirmImport(batchId, request) {
      const response = await client.post<{ snapshot: SchedulingSnapshot }>(
        injectionSchedulingEndpoints.importConfirm(batchId),
        {
          factory_id: request.factoryId,
          preview_revision: request.previewRevision,
          reason: request.reason,
        },
        { timeout: 120_000 },
      )
      return response.data.snapshot
    },
    async rollbackVersion(request) {
      const response = await client.post<{ snapshot: SchedulingSnapshot }>(
        injectionSchedulingEndpoints.rollbackVersion,
        {
          factory_id: request.factoryId,
          revision: request.revision,
          version: request.version,
          reason: request.reason,
        },
      )
      return response.data.snapshot
    },
  }
}

export const injectionSchedulingRepository = createHttpInjectionSchedulingRepository()
