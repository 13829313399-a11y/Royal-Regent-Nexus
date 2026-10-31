import { afterEach, expect, it } from 'vitest'
import { http } from '@/lib/http'
import { cartonOrderImportApi, type ImportConfirm } from '../cartonOrderImport'
import { cartonBatchOrdersApi } from '../cartonBatchOrders'

const adapter = http.defaults.adapter
afterEach(() => { http.defaults.adapter = adapter })
it('preserves workbook bytes and JSON command as multipart through the real Axios transforms', async () => {
  const file = new File(['workbook-bytes'], '自有表.xlsx')
  let calls = 0
  http.defaults.adapter = async config => {
    calls++
    expect(config.data).toBeInstanceOf(FormData)
    expect((config.data as FormData).get('file')).toBe(file)
    expect(config.headers.getContentType()).toContain('multipart/form-data')
    expect(JSON.parse(String((config.data as FormData).get('body')))).toMatchObject({ factory_id: 'huaxing' })
    return { data: {}, status: 200, statusText: 'OK', headers: {}, config }
  }
  const body: ImportConfirm = { factory_id: 'huaxing', mode: 'REGULAR', fingerprint: 'a'.repeat(64), rows: [], request_id: 'request-123456789', selected_groups: ['G-2'], preview_fingerprint: 'b'.repeat(64) }
  await cartonOrderImportApi.read({ factory_id: body.factory_id, mode: body.mode }, file)
  await cartonOrderImportApi.preview(body, file)
  await cartonOrderImportApi.confirm(body, file)
  await cartonBatchOrdersApi.importDemands({ factory_id: 'huaxing', request_id: 'legacy-123456789', fingerprint: 'a'.repeat(64), rows: [] }, file)
  expect(calls).toBe(4)
})
