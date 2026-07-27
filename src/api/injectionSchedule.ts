import { http } from '@/lib/http'
import type {
  InjectionAutomationResult,
  InjectionAutoDraftInput,
  InjectionDraftCreateInput,
  InjectionImportBatch,
  InjectionImportConfirmInput,
  InjectionMachineCreateInput,
  InjectionMachineRecord,
  InjectionMachineUpdateInput,
  InjectionMoldCreateInput,
  InjectionMoldRecord,
  InjectionMoldUpdateInput,
  InjectionOrderCreateInput,
  InjectionOrderRecommendationResponse,
  InjectionOrderRecord,
  InjectionOrderUpdateInput,
  InjectionPlanVersion,
  InjectionPlanVersionDetail,
  InjectionReplanInput,
  InjectionScheduleRuleConfigUpdateInput,
  InjectionScheduleRuleConfigV3,
  InjectionScheduleOperationRequest,
  InjectionScheduleOperationResult,
  InjectionScheduleWorkspace,
  InjectionShiftActual,
  InjectionShiftActualCorrectionInput,
  InjectionShiftActualCreateInput,
  InjectionShiftActualListOptions,
  InjectionShiftActualResult,
  InjectionValidationResult,
  InjectionVersionCloneInput,
  InjectionVersionDiff,
  InjectionVersionPublishInput,
} from '@/types/injectionSchedule'

export interface InjectionScheduleHttpClient {
  get<T = unknown>(url: string, config?: unknown): Promise<{ data: T }>
  post<T = unknown>(url: string, data?: unknown, config?: unknown): Promise<{ data: T }>
  patch<T = unknown>(url: string, data?: unknown, config?: unknown): Promise<{ data: T }>
}

type JsonRecord = Record<string, unknown>

function isPlainRecord(value: unknown): value is JsonRecord {
  return Boolean(value)
    && typeof value === 'object'
    && !Array.isArray(value)
    && !(value instanceof Date)
    && !(value instanceof File)
    && !(value instanceof Blob)
    && !(value instanceof FormData)
}

function camelKey(value: string) {
  return value.replace(/_([a-z0-9])/g, (_, letter: string) => letter.toUpperCase())
}

function snakeKey(value: string) {
  return value.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`)
}

function mapKeys(value: unknown, keyMapper: (key: string) => string): unknown {
  if (Array.isArray(value)) {
    return value.map((entry) => mapKeys(entry, keyMapper))
  }
  if (!isPlainRecord(value)) return value

  return Object.fromEntries(
    Object.entries(value).map(([key, entry]) => [
      keyMapper(key),
      mapKeys(entry, keyMapper),
    ]),
  )
}

function fromApi<T>(value: unknown): T {
  return mapKeys(value, camelKey) as T
}

function toApi(value: unknown): unknown {
  return mapKeys(value, snakeKey)
}

function scopedBase(factoryId: string) {
  return `/factories/${encodeURIComponent(factoryId)}/injection-schedule`
}

function versionPath(factoryId: string, versionId: string) {
  return `${scopedBase(factoryId)}/versions/${encodeURIComponent(versionId)}`
}

function masterPath(
  factoryId: string,
  kind: 'machines' | 'molds' | 'orders',
  recordId?: string,
) {
  const base = `${scopedBase(factoryId)}/${kind}`
  return recordId ? `${base}/${encodeURIComponent(recordId)}` : base
}

function normalizedReason(
  reason: string,
  minimumLength = 1,
  message = '排程变更原因不能为空',
) {
  const value = reason.trim()
  if (value.length < minimumLength) throw new Error(message)
  return value
}

function assertPhase4PreviewContext(
  dryRun: boolean | undefined,
  expectedContextHash: string | undefined,
) {
  if (dryRun === true) return
  if (!/^[a-f0-9]{64}$/i.test(expectedContextHash?.trim() ?? '')) {
    throw new Error('应用 Phase 4 排程前必须先预览并携带 64 位上下文哈希')
  }
}

function operationRequestToApi(input: InjectionScheduleOperationRequest) {
  if (input.commands.length < 1 || input.commands.length > 100) {
    throw new Error('每次排程变更必须包含 1 至 100 条命令')
  }
  return toApi({
    expectedRevision: input.expectedRevision,
    reason: normalizedReason(input.reason),
    requestId: input.requestId ?? '',
    commands: input.commands.map((command) => {
      const {
        manualConfirmation,
        // The command reason is a local optimistic label. The authoritative
        // audit reason belongs to the command envelope.
        reason: _localReason,
        ...payload
      } = command
      const manualConfirmationReason = manualConfirmation?.reason.trim() ?? ''
      if (
        manualConfirmation?.confirmed === true
        && manualConfirmationReason.length < 4
      ) {
        throw new Error('人工确认原因至少填写 4 个字符')
      }
      return {
        ...payload,
        manualConfirmation: manualConfirmation?.confirmed === true,
        manualConfirmationReason,
      }
    }),
  })
}

export function createInjectionScheduleApi(
  client: InjectionScheduleHttpClient = http,
) {
  return {
    async getWorkspace(factoryId: string, versionId?: string) {
      const response = await client.get<unknown>(`${scopedBase(factoryId)}/workspace`, {
        params: versionId ? { version_id: versionId } : {},
      })
      return fromApi<InjectionScheduleWorkspace>(response.data)
    },

    async previewImport(factoryId: string, file: File) {
      const form = new FormData()
      form.append('file', file)
      const response = await client.post<unknown>(
        `${scopedBase(factoryId)}/imports`,
        form,
        {
          headers: { 'Content-Type': 'multipart/form-data' },
          timeout: 120_000,
        },
      )
      return fromApi<InjectionImportBatch>(response.data)
    },

    async listImports(factoryId: string) {
      const response = await client.get<unknown>(`${scopedBase(factoryId)}/imports`)
      return fromApi<InjectionImportBatch[]>(response.data)
    },

    async getImport(factoryId: string, batchId: string) {
      const response = await client.get<unknown>(
        `${scopedBase(factoryId)}/imports/${encodeURIComponent(batchId)}`,
      )
      return fromApi<InjectionImportBatch>(response.data)
    },

    async confirmImport(
      factoryId: string,
      batchId: string,
      input: InjectionImportConfirmInput,
    ) {
      const response = await client.post<unknown>(
        `${scopedBase(factoryId)}/imports/${encodeURIComponent(batchId)}/confirm`,
        toApi({
          ...input,
          reason: normalizedReason(
            input.reason,
            4,
            '导入确认原因至少填写 4 个字符',
          ),
        }),
      )
      return fromApi<InjectionImportBatch>(response.data)
    },

    async listMachines(factoryId: string) {
      const response = await client.get<unknown>(masterPath(factoryId, 'machines'))
      return fromApi<InjectionMachineRecord[]>(response.data)
    },

    async createMachine(factoryId: string, input: InjectionMachineCreateInput) {
      const response = await client.post<unknown>(
        masterPath(factoryId, 'machines'),
        toApi(input),
      )
      return fromApi<InjectionMachineRecord>(response.data)
    },

    async updateMachine(
      factoryId: string,
      machineId: string,
      expectedRevision: number,
      input: InjectionMachineUpdateInput,
    ) {
      const response = await client.patch<unknown>(
        masterPath(factoryId, 'machines', machineId),
        toApi({ expectedRevision, ...input }),
      )
      return fromApi<InjectionMachineRecord>(response.data)
    },

    async listMolds(factoryId: string) {
      const response = await client.get<unknown>(masterPath(factoryId, 'molds'))
      return fromApi<InjectionMoldRecord[]>(response.data)
    },

    async createMold(factoryId: string, input: InjectionMoldCreateInput) {
      const response = await client.post<unknown>(
        masterPath(factoryId, 'molds'),
        toApi(input),
      )
      return fromApi<InjectionMoldRecord>(response.data)
    },

    async updateMold(
      factoryId: string,
      moldId: string,
      expectedRevision: number,
      input: InjectionMoldUpdateInput,
    ) {
      const response = await client.patch<unknown>(
        masterPath(factoryId, 'molds', moldId),
        toApi({ expectedRevision, ...input }),
      )
      return fromApi<InjectionMoldRecord>(response.data)
    },

    async listOrders(factoryId: string) {
      const response = await client.get<unknown>(masterPath(factoryId, 'orders'))
      return fromApi<InjectionOrderRecord[]>(response.data)
    },

    async createOrder(factoryId: string, input: InjectionOrderCreateInput) {
      const response = await client.post<unknown>(
        masterPath(factoryId, 'orders'),
        toApi(input),
      )
      return fromApi<InjectionOrderRecord>(response.data)
    },

    async updateOrder(
      factoryId: string,
      orderId: string,
      expectedRevision: number,
      input: InjectionOrderUpdateInput,
    ) {
      const response = await client.patch<unknown>(
        masterPath(factoryId, 'orders', orderId),
        toApi({ expectedRevision, ...input }),
      )
      return fromApi<InjectionOrderRecord>(response.data)
    },

    async listVersions(factoryId: string) {
      const response = await client.get<unknown>(`${scopedBase(factoryId)}/versions`)
      return fromApi<InjectionPlanVersion[]>(response.data)
    },

    async createDraftVersion(factoryId: string, input: InjectionDraftCreateInput) {
      const response = await client.post<unknown>(
        `${scopedBase(factoryId)}/versions`,
        toApi(input),
      )
      return fromApi<InjectionPlanVersion>(response.data)
    },

    async getVersion(factoryId: string, versionId: string) {
      const response = await client.get<unknown>(versionPath(factoryId, versionId))
      return fromApi<InjectionPlanVersionDetail>(response.data)
    },

    async executeOperations(
      factoryId: string,
      versionId: string,
      input: InjectionScheduleOperationRequest,
    ) {
      const response = await client.post<unknown>(
        `${versionPath(factoryId, versionId)}/commands`,
        operationRequestToApi(input),
      )
      return fromApi<InjectionScheduleOperationResult>(response.data)
    },

    async validateVersion(
      factoryId: string,
      versionId: string,
      expectedRevision: number,
    ) {
      const response = await client.post<unknown>(
        `${versionPath(factoryId, versionId)}/validate`,
        { expected_revision: expectedRevision },
      )
      return fromApi<InjectionValidationResult>(response.data)
    },

    async getVersionDiff(
      factoryId: string,
      versionId: string,
      againstVersionId?: string | null,
    ) {
      const path = `${versionPath(factoryId, versionId)}/diff`
      const response = againstVersionId
        ? await client.get<unknown>(
            path,
            { params: { against_version_id: againstVersionId } },
          )
        : await client.get<unknown>(path)
      return fromApi<InjectionVersionDiff>(response.data)
    },

    async getRecommendations(
      factoryId: string,
      versionId: string,
      orderId: string,
      options: { limit?: number; plannedQty?: number } = {},
    ) {
      const params: Record<string, number> = {}
      if (options.limit != null) params.limit = options.limit
      if (options.plannedQty != null) params.planned_qty = options.plannedQty
      const response = await client.get<unknown>(
        `${versionPath(factoryId, versionId)}/orders/${encodeURIComponent(orderId)}/recommendations`,
        { params },
      )
      return fromApi<InjectionOrderRecommendationResponse>(response.data)
    },

    async generateAutoDraft(
      factoryId: string,
      versionId: string,
      input: InjectionAutoDraftInput,
    ) {
      assertPhase4PreviewContext(input.dryRun, input.expectedContextHash)
      const response = await client.post<unknown>(
        `${versionPath(factoryId, versionId)}/auto-draft`,
        toApi({
          ...input,
          reason: normalizedReason(
            input.reason,
            4,
            '自动排程原因至少填写 4 个字符',
          ),
        }),
      )
      return fromApi<InjectionAutomationResult>(response.data)
    },

    async replanVersion(
      factoryId: string,
      versionId: string,
      input: InjectionReplanInput,
    ) {
      assertPhase4PreviewContext(input.dryRun, input.expectedContextHash)
      const response = await client.post<unknown>(
        `${versionPath(factoryId, versionId)}/replan`,
        toApi({
          ...input,
          reason: normalizedReason(
            input.reason,
            4,
            '局部重排原因至少填写 4 个字符',
          ),
          trigger: {
            ...input.trigger,
            reason: normalizedReason(
              input.trigger.reason,
              4,
              '局部重排触发原因至少填写 4 个字符',
            ),
          },
        }),
      )
      return fromApi<InjectionAutomationResult>(response.data)
    },

    async listActuals(
      factoryId: string,
      options: InjectionShiftActualListOptions = {},
    ) {
      const params: Record<string, string> = {}
      if (options.versionId) params.version_id = options.versionId
      if (options.dateFrom) params.date_from = options.dateFrom
      if (options.dateTo) params.date_to = options.dateTo
      const response = await client.get<unknown>(
        `${scopedBase(factoryId)}/actuals`,
        { params },
      )
      return fromApi<InjectionShiftActual[]>(response.data)
    },

    async writeActual(
      factoryId: string,
      input: InjectionShiftActualCreateInput,
    ) {
      const response = await client.post<unknown>(
        `${scopedBase(factoryId)}/actuals`,
        toApi({
          ...input,
          reason: normalizedReason(
            input.reason,
            4,
            '实绩回写原因至少填写 4 个字符',
          ),
        }),
      )
      return fromApi<InjectionShiftActualResult>(response.data)
    },

    async correctActual(
      factoryId: string,
      actualId: string,
      input: InjectionShiftActualCorrectionInput,
    ) {
      const response = await client.patch<unknown>(
        `${scopedBase(factoryId)}/actuals/${encodeURIComponent(actualId)}`,
        toApi({
          ...input,
          reason: normalizedReason(
            input.reason,
            4,
            '实绩更正原因至少填写 4 个字符',
          ),
        }),
      )
      return fromApi<InjectionShiftActualResult>(response.data)
    },

    async getRuleConfig(factoryId: string) {
      const response = await client.get<unknown>(
        `${scopedBase(factoryId)}/rule-config`,
      )
      return fromApi<InjectionScheduleRuleConfigV3>(response.data)
    },

    async updateRuleConfig(
      factoryId: string,
      input: InjectionScheduleRuleConfigUpdateInput,
    ) {
      const reason = normalizedReason(
        input.reason,
        4,
        '规则配置变更原因至少填写 4 个字符',
      )
      const response = await client.patch<unknown>(
        `${scopedBase(factoryId)}/rule-config`,
        toApi({ ...input, reason }),
      )
      return fromApi<InjectionScheduleRuleConfigV3>(response.data)
    },

    async publishVersion(
      factoryId: string,
      versionId: string,
      input: InjectionVersionPublishInput,
    ) {
      const response = await client.post<unknown>(
        `${versionPath(factoryId, versionId)}/publish`,
        toApi({ ...input, reason: normalizedReason(input.reason) }),
      )
      return fromApi<InjectionPlanVersion>(response.data)
    },

    async cloneVersionAsDraft(
      factoryId: string,
      versionId: string,
      input: InjectionVersionCloneInput,
    ) {
      const response = await client.post<unknown>(
        `${versionPath(factoryId, versionId)}/clone`,
        toApi({ ...input, reason: normalizedReason(input.reason) }),
      )
      return fromApi<InjectionPlanVersion>(response.data)
    },
  }
}

export const injectionScheduleApi = createInjectionScheduleApi()
