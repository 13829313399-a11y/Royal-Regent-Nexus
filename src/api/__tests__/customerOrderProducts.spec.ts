import { beforeEach, expect, it, vi } from 'vitest'
import { customerOrderProductsApi } from '../customerOrderProducts'
import { createCustomerOrderApi } from '../customerOrder'
const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/lib/http', () => ({ http }))
beforeEach(() => { vi.resetAllMocks(); http.get.mockResolvedValue({ data: {} }); http.post.mockResolvedValue({ data: {}, headers: {} }) })
const choice = { product_no: '000123', item_sheet_name: 'ITEM表', product_name_zh: '测试', product_name_en: 'Test', default_pack: '12', reason: '已核对分类' }
it('catalog writes are JSON, scoped and carry the page-only header and revision', async () => {
  const signal = new AbortController().signal
  await customerOrderProductsApi.catalog(signal)
  expect(http.get).toHaveBeenCalledWith('/customer-order-product-rules?factory_id=huaxing&customer_code=dickie', { signal })
  await customerOrderProductsApi.save({ ...choice, expected_revision: 7, active: true }, signal)
  expect(http.post).toHaveBeenCalledWith('/customer-order-product-rules?factory_id=huaxing&customer_code=dickie',
    { ...choice, expected_revision: 7, active: true }, { signal, headers: { 'X-Order-Product-Rules': '1' } })
})
it('the same one-off choices are included in both preview and export only when supplied', async () => {
  const api = createCustomerOrderApi(http)
  const po = new File(['test'], 'PO.pdf'), schedule = new File(['test'], 'schedule.xlsx')
  await api.previewDickieBatch([po], schedule, '2026-10-14', 'huaxing', [choice])
  expect(JSON.parse(String((http.post.mock.calls[0]![1] as FormData).get('product_choices')))).toEqual([choice])
  await api.exportDickieBatch([po], schedule, '2026-10-14', 'out.xlsx', 'huaxing', [], 'fingerprint', '', [], [choice])
  const body = http.post.mock.calls[1]![1] as FormData
  expect(body.get('preview_fingerprint')).toBe('fingerprint')
  expect(JSON.parse(String(body.get('product_choices')))).toEqual([choice])
  await api.previewDickieBatch([po], schedule, '2026-10-14')
  expect((http.post.mock.calls[2]![1] as FormData).has('product_choices')).toBe(false)
})
