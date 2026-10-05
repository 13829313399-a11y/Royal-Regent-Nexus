import { beforeEach, describe, expect, it, vi } from 'vitest'
import { cartonProcurementApi } from '../cartonProcurement'
import type { CartonOrderResponse } from '../cartonProcurement'
const get = vi.hoisted(() => vi.fn())
const post = vi.hoisted(() => vi.fn())
vi.mock('@/lib/http', () => ({ http: { get, post } }))

describe('carton history pagination', () => {
  beforeEach(() => get.mockReset())
  it.each(['listOrders', 'listReceipts'] as const)('loads %s beyond the first 200 records', async (method) => {
    const first = Array.from({ length: 200 }, (_, index) => ({ id: `row-${index}` }))
    get.mockResolvedValueOnce({ data: { items: first, total: 201 } })
      .mockResolvedValueOnce({ data: { items: [{ id: 'old-record' }], total: 201 } })
    const result = await cartonProcurementApi[method]('huaxing')
    expect(result).toHaveLength(201)
    expect(result[200]?.id).toBe('old-record')
    expect(get.mock.calls[1]?.[1].params).toMatchObject({ factory_id: 'huaxing', offset: 200 })
  })
})

it('retries direct receipt posting with the same request identity after a lost response', async () => {
  post.mockReset()
  const payload = { factory_id: 'huaxing', post_immediately: true, delivery_note_no: 'DN-RETRY',
    delivery_date: '2026-09-08', import_batch_id: null, note: '', lines: [] }
  post.mockRejectedValueOnce(new Error('lost response'))
  await expect(cartonProcurementApi.createReceipt(payload)).rejects.toThrow('lost response')
  const requestId = post.mock.calls[0]?.[1].request_id
  expect(requestId).toBeTruthy()
  post.mockResolvedValueOnce({ data: { id: 'R-POSTED', status: 'POSTED' } })
  expect(await cartonProcurementApi.createReceipt(payload)).toMatchObject({ status: 'POSTED' })
  expect(post.mock.calls[1]).toEqual(['/carton-procurement/receipts', { ...payload, request_id: requestId }])
})

it('sends every selected history revision in one atomic deletion request', async () => {
  post.mockReset().mockResolvedValue({ data: null })
  const orders = [{ order_no: 'H-A', revision: 2 }, { order_no: 'H-B', revision: 5 }] as CartonOrderResponse[]
  await cartonProcurementApi.bulkDeleteHistoryOrders('huaxing', orders, '重复导入需要删除')
  expect(post).toHaveBeenCalledExactlyOnceWith('/carton-procurement/orders/bulk-delete-history', {
    factory_id: 'huaxing', reason: '重复导入需要删除', items: [
      { order_no: 'H-A', expected_revision: 2 }, { order_no: 'H-B', expected_revision: 5 },
    ],
  })
})

it('undoes the entire import batch with factory and reason and no row selection', async () => {
  post.mockReset().mockResolvedValue({ data: { id: 'BATCH-1', status: 'REJECTED' } })
  expect(await cartonProcurementApi.undoScheduleImport('huaxing', 'BATCH-1', '本次导入文件有误')).toEqual({ id: 'BATCH-1', status: 'REJECTED' })
  expect(post).toHaveBeenCalledExactlyOnceWith('/carton-procurement/imports/BATCH-1/undo', {
    factory_id: 'huaxing', reason: '本次导入文件有误',
  })
})

it('polls a file job before completing it and never writes after parser failure', async () => {
  vi.useFakeTimers()
  get.mockReset(); post.mockReset()
  try {
    post.mockResolvedValueOnce({ data: { id: 'J', status: 'PROCESSING' } })
      .mockResolvedValueOnce({ data: { id: 'BATCH' } })
    get.mockResolvedValueOnce({ data: { id: 'J', status: 'PROCESSING' } })
      .mockResolvedValueOnce({ data: { id: 'J', status: 'READY' } })
    const pending = cartonProcurementApi.uploadWeeklySchedule('huakang-b', new File(['xlsx'], 'schedule.xlsx'), 'TEST')
    await vi.advanceTimersByTimeAsync(750)
    expect(post).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(750)
    expect(await pending).toEqual({ id: 'BATCH' })
    expect(post.mock.calls[1]).toEqual(['/carton-procurement/file-jobs/J/complete', null,
      { params: { factory_id: 'huakang-b' }, timeout: 60_000 }])
    post.mockReset().mockResolvedValueOnce({ data: { id: 'FAIL', status: 'FAILED', error: '文件超限，整批未导入' } })
    await expect(cartonProcurementApi.uploadReceipt('huakang-b', new File(['bad'], 'bad.xlsx'))).rejects.toThrow('文件超限')
    expect(post).toHaveBeenCalledTimes(1)
  } finally { vi.useRealTimers() }
})
