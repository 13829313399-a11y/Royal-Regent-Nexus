import { http } from '../lib/http.js'
import type {
  InjectionScheduleImportPreview,
  InjectionScheduleMachine,
} from '../types/injectionSchedule.js'

export interface InjectionScheduleHttpClient {
  get<T = unknown>(url: string, config?: unknown): Promise<{ data: T }>
  post<T = unknown>(url: string, data?: unknown, config?: unknown): Promise<{ data: T }>
}

export function createInjectionScheduleApi(client: InjectionScheduleHttpClient = http) {
  return {
    async importDailySchedule(file: File, factoryId = 'huaxing') {
      const payload = new FormData()
      payload.append('factory_id', factoryId)
      payload.append('file', file)

      const response = await client.post<InjectionScheduleImportPreview>(
        '/injection-scheduling/imports/daily-schedule',
        payload,
        {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        },
      )
      return response.data
    },
    async getImportPreview(batchId: string) {
      const response = await client.get<InjectionScheduleImportPreview>(
        `/injection-scheduling/imports/${encodeURIComponent(batchId)}/preview`,
      )
      return response.data
    },
    async getMachineStatus(batchId: string) {
      const response = await client.get<InjectionScheduleMachine[]>(
        `/injection-scheduling/machines/status?batch_id=${encodeURIComponent(batchId)}`,
      )
      return response.data
    },
  }
}

export const injectionScheduleApi = createInjectionScheduleApi()
