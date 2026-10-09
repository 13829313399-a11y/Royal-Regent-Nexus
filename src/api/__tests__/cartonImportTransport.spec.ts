import { afterEach, expect, it } from 'vitest'
import type { InternalAxiosRequestConfig } from 'axios'
import { http } from '@/lib/http'
import { cartonProcurementApi } from '../cartonProcurement'

const originalAdapter = http.defaults.adapter
afterEach(() => { http.defaults.adapter = originalAdapter })

it('sends the selected schedule customer with the untouched file and factory through Axios', async () => {
  const requests: InternalAxiosRequestConfig[] = []
  http.defaults.adapter = async config => {
    requests.push(config)
    return { data: { id: 'JOB-1', status: 'READY' }, status: 200, statusText: 'OK', headers: {}, config }
  }
  const file = new File(['schedule-test-bytes'], '业务排期.xlsx')
  await cartonProcurementApi.uploadWeeklySchedule('huaxing', file, 'DICKIE')
  const request = requests[0]!
  expect(request.url).toBe('/carton-procurement/file-jobs/imports')
  expect(request.params).toEqual({ factory_id: 'huaxing', import_type: 'WEEKLY_SCHEDULE', advance_days: 3 })
  expect(request.data).toBeInstanceOf(FormData)
  expect(request.data.get('file')).toBe(file)
  expect(request.data.get('customer_code')).toBe('DICKIE')
  expect(request.headers.getContentType()).toBe('multipart/form-data')
  expect(requests[1]!.url).toBe('/carton-procurement/file-jobs/JOB-1/complete')
  expect(requests[1]!.params).toEqual({ factory_id: 'huaxing' })
})

it('preserves Excel files through the real Axios transforms for previews and confirmation', async () => {
  const requests: InternalAxiosRequestConfig[] = []
  http.defaults.adapter = async (config) => {
    requests.push(config)
    return { data: {}, status: 200, statusText: 'OK', headers: {}, config }
  }
  const file = new File(['xlsx-test-bytes'], 'history.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
  const options = { customer_name: '迪奇', warehouse: 'A', snapshot_date: '2026-08-31', dimension_unit: 'cm' as const, currency: 'CNY' }
  await cartonProcurementApi.previewHistoryOrders('huaxing', file)
  await cartonProcurementApi.uploadHistoryOrders('huaxing', file, 'orders-fingerprint')
  await cartonProcurementApi.previewHistoryInventory('huaxing', file, options)
  await cartonProcurementApi.uploadHistoryInventory('huaxing', file, options, 'inventory-fingerprint')
  expect(requests).toHaveLength(4)
  for (const request of requests) {
    expect(request.data).toBeInstanceOf(FormData)
    expect(request.data.get('file')).toBe(file)
    expect(request.headers.getContentType()).toBe('multipart/form-data')
    expect(request.params).toEqual({ factory_id: 'huaxing' })
  }
  expect(requests[1]!.data.get('expected_preview_fingerprint')).toBe('orders-fingerprint')
  expect(requests[2]!.data.get('options')).toBe(JSON.stringify(options))
  expect(requests[3]!.data.get('options')).toBe(JSON.stringify(options))
  expect(requests[3]!.data.get('expected_preview_fingerprint')).toBe('inventory-fingerprint')
})
