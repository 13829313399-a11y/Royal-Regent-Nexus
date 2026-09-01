import { http } from '@/lib/http'
import type {
  InjectionScheduleBoard,
  InjectionScheduleBootstrap,
  InjectionScheduleList,
  InjectionScheduleImportCommitResult,
  InjectionScheduleImportPreview,
  InjectionScheduleMachine,
  InjectionScheduleMold,
  InjectionScheduleOrder,
  InjectionScheduleAutoProposal,
  InjectionScheduleMovePayload,
  InjectionScheduleMoveValidation,
  InjectionScheduleSavedView,
} from '@/types/injectionScheduling'

const BASE_PATH = '/production/injection-scheduling'

export interface InjectionScheduleOrderFilters {
  search?: string
  status?: string
  priority?: string
}

export const injectionSchedulingApi = {
  async bootstrap(factoryId: string) {
    const response = await http.get<InjectionScheduleBootstrap>(`${BASE_PATH}/bootstrap`, {
      params: { factory_id: factoryId },
    })
    return response.data
  },

  async board(factoryId: string, startDate = '', endDate = '') {
    const response = await http.get<InjectionScheduleBoard>(`${BASE_PATH}/board`, {
      params: {
        factory_id: factoryId,
        ...(startDate ? { start_date: startDate } : {}),
        ...(endDate ? { end_date: endDate } : {}),
      },
    })
    return response.data
  },

  async orders(factoryId: string, filters: InjectionScheduleOrderFilters = {}) {
    const response = await http.get<InjectionScheduleList<InjectionScheduleOrder>>(
      `${BASE_PATH}/orders`,
      {
        params: {
          factory_id: factoryId,
          search: filters.search ?? '',
          status: filters.status ?? '',
          priority: filters.priority ?? '',
        },
      },
    )
    return response.data
  },

  async machines(factoryId: string) {
    const response = await http.get<InjectionScheduleList<InjectionScheduleMachine>>(
      `${BASE_PATH}/machines`,
      { params: { factory_id: factoryId } },
    )
    return response.data
  },

  async molds(factoryId: string) {
    const response = await http.get<InjectionScheduleList<InjectionScheduleMold>>(
      `${BASE_PATH}/molds`,
      { params: { factory_id: factoryId } },
    )
    return response.data
  },

  async downloadUnifiedTemplate(factoryId: string) {
    const response = await http.get<Blob>(`${BASE_PATH}/templates/unified-plan`, {
      params: { factory_id: factoryId },
      responseType: 'blob',
      timeout: 60_000,
    })
    return response.data
  },

  async previewImport(factoryId: string, file: File, requestId: string, profileOverride = '') {
    const form = new FormData()
    form.append('factory_id', factoryId)
    form.append('request_id', requestId)
    form.append('profile_override', profileOverride)
    form.append('file', file, file.name)
    const response = await http.post<InjectionScheduleImportPreview>(
      `${BASE_PATH}/imports/preview`,
      form,
      {
        timeout: 60_000,
        headers: { 'Content-Type': 'multipart/form-data' },
      },
    )
    return response.data
  },

  async commitImport(factoryId: string, batchId: string, requestId: string) {
    const response = await http.post<InjectionScheduleImportCommitResult>(
      `${BASE_PATH}/imports/${batchId}/commit`,
      { factory_id: factoryId, request_id: requestId },
      { timeout: 60_000 },
    )
    return response.data
  },

  async rejectImport(factoryId: string, batchId: string, reason = '') {
    const response = await http.post<InjectionScheduleImportPreview>(
      `${BASE_PATH}/imports/${batchId}/reject`,
      { factory_id: factoryId, reason },
    )
    return response.data
  },

  async savedViews(factoryId: string) {
    const response = await http.get<InjectionScheduleSavedView[]>(`${BASE_PATH}/saved-views`, {
      params: { factory_id: factoryId },
    })
    return response.data
  },

  async createSavedView(factoryId: string, name: string, config: InjectionScheduleSavedView['config']) {
    const response = await http.post<InjectionScheduleSavedView>(`${BASE_PATH}/saved-views`, {
      factory_id: factoryId,
      name,
      scope: 'PERSONAL',
      config,
      is_default: false,
    })
    return response.data
  },

  async exportTable(factoryId: string, filters: InjectionScheduleOrderFilters) {
    const response = await http.post<Blob>(
      `${BASE_PATH}/exports/table`,
      {
        factory_id: factoryId,
        columns: [],
        search: filters.search ?? '',
        status: filters.status ?? '',
        priority: filters.priority ?? '',
      },
      { responseType: 'blob', timeout: 60_000 },
    )
    return response.data
  },

  async validateMove(lineId: string, payload: InjectionScheduleMovePayload) {
    const response = await http.post<InjectionScheduleMoveValidation>(
      `${BASE_PATH}/schedule-lines/${lineId}/validate-move`,
      payload,
    )
    return response.data
  },

  async moveLine(lineId: string, payload: InjectionScheduleMovePayload) {
    const response = await http.post(`${BASE_PATH}/schedule-lines/${lineId}/move`, payload)
    return response.data
  },

  async lineAction(
    lineId: string,
    action: 'lock' | 'unlock' | 'pause' | 'resume',
    factoryId: string,
    lineVersion: number,
    scheduleRevision: number,
    reason: string,
  ) {
    const response = await http.post(`${BASE_PATH}/schedule-lines/${lineId}/${action}`, {
      factory_id: factoryId,
      expected_line_version: lineVersion,
      expected_schedule_revision: scheduleRevision,
      reason,
    })
    return response.data
  },

  async putShiftOutput(
    factoryId: string,
    lineId: string,
    productionDate: string,
    shift: 'DAY' | 'NIGHT',
    reportedShots: string,
    defectShots: string,
  ) {
    const response = await http.put(
      `${BASE_PATH}/schedule-lines/${lineId}/shift-outputs/${productionDate}/${shift}`,
      {
        factory_id: factoryId,
        reported_shots: reportedShots,
        defect_shots: defectShots,
      },
    )
    return response.data
  },

  async previewAutoSchedule(
    factoryId: string,
    requestId: string,
    startAt: string,
    endAt: string,
    expectedRevision: number,
  ) {
    const response = await http.post<InjectionScheduleAutoProposal>(`${BASE_PATH}/auto-schedule/preview`, {
      factory_id: factoryId,
      request_id: requestId,
      start_at: startAt,
      end_at: endAt,
      mode: 'INCREMENTAL',
      selected_order_ids: [],
      affected_machine_ids: [],
      expected_schedule_revision: expectedRevision,
    })
    return response.data
  },

  async applyAutoSchedule(factoryId: string, proposalId: string, expectedRevision: number) {
    const response = await http.post<InjectionScheduleAutoProposal>(
      `${BASE_PATH}/auto-schedule/proposals/${proposalId}/apply`,
      {
        factory_id: factoryId,
        expected_schedule_revision: expectedRevision,
        reason: '用户确认自动排程预览',
      },
    )
    return response.data
  },
}
