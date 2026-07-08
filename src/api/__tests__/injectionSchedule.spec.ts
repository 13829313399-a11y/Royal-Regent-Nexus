import { describe, expect, it } from 'vitest'
import { createInjectionScheduleApi } from '../injectionSchedule'

describe('injectionScheduleApi', () => {
  it('uses the independent injection scheduling API namespace', async () => {
    const calls: Array<{ method: string; url: string; data?: unknown }> = []
    const client = {
      async get(url: string) {
        calls.push({ method: 'get', url })
        return { data: { url } }
      },
      async post(url: string, data?: unknown) {
        calls.push({ method: 'post', url, data })
        return { data: { url } }
      },
    }
    const api = createInjectionScheduleApi(client)
    const file = new File(['xlsx'], 'daily.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })

    await api.importDailySchedule(file, 'huaxing')
    await api.getImportPreview('batch-1')
    await api.getMachineStatus('batch-1')

    expect(calls.map((call) => `${call.method} ${call.url}`)).toEqual([
      'post /injection-scheduling/imports/daily-schedule',
      'get /injection-scheduling/imports/batch-1/preview',
      'get /injection-scheduling/machines/status?batch_id=batch-1',
    ])
    expect(calls[0].data).toBeInstanceOf(FormData)
    expect((calls[0].data as FormData).get('factory_id')).toBe('huaxing')
    expect((calls[0].data as FormData).get('file')).toBe(file)
  })
})
