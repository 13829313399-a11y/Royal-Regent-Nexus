import { beforeEach, describe, expect, it, vi } from 'vitest'
import { indonesiaMaterialsApi } from '@/api/indonesiaMaterials'
const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/lib/http', () => ({ http }))
beforeEach(() => vi.resetAllMocks())
describe('materials API contract', () => {
  it('passes explicit factory scope and the workspace envelope unchanged', async () => {
    const body = { records: [], board: [], permissions: ['read'] }
    http.get.mockResolvedValue({ data: body })
    expect(await indonesiaMaterialsApi.workspace('huaxing')).toEqual(body)
    expect(http.get).toHaveBeenCalledWith('/indonesia-materials/workspace', { params: { factory_id: 'huaxing' } })
  })
  it('uses the multipart source preview envelope without inventing client row IDs', async () => {
    const record = { id: 'preview', kind: 'import', version: 1, data: { rows: [{ index: 7, blocked: true, issues: ['缺货号'] }] } }
    const file = new File(['xlsx'], 'schedule.xlsx')
    http.post.mockResolvedValue({ data: { record } })
    expect(await indonesiaMaterialsApi.preview('huadeng', 'TEST', 'RRM', file)).toEqual({ record })
    const [path, form, options] = http.post.mock.calls[0]!
    expect(path).toBe('/indonesia-materials/imports/preview')
    expect(form.get('factory_id')).toBe('huadeng')
    expect(form.get('customer')).toBe('TEST')
    expect(form.get('recipient')).toBe('RRM')
    expect(form.get('file')).toBe(file)
    expect(options.timeout).toBe(120_000)
  })
  it.each(['shipment', 'asset'] as const)('downloads %s bytes using the server record and factory', async kind => {
    const blob = new Blob(['xlsx'])
    http.get.mockResolvedValue({ data: blob })
    expect(await indonesiaMaterialsApi.download('huaxing', 'id/one', kind)).toBe(blob)
    expect(http.get).toHaveBeenCalledWith(`/indonesia-materials/${kind === 'shipment' ? 'shipments/id%2Fone/export' : 'assets/id%2Fone'}`, { params: { factory_id: 'huaxing' }, responseType: 'blob', timeout: 120_000 })
  })
  it('sends warehouse documents to their own preview endpoint and preserves the selected warehouse', async () => {
    const file = new File(['csv'], 'receipt.csv')
    http.post.mockResolvedValue({ data: { record: { id: 'receipt', kind: 'import' } } })
    await indonesiaMaterialsApi.preview('huaxing', 'CLIENT', 'RRM', file, '塑胶仓')
    const [path, form] = http.post.mock.calls[0]!
    expect(path).toBe('/indonesia-materials/warehouse-imports/preview')
    expect(form.get('warehouse')).toBe('塑胶仓')
    expect(form.get('factory_id')).toBe('huaxing')
    expect(form.get('file')).toBe(file)
  })
})
