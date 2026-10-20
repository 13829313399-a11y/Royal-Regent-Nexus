import { afterEach, describe, expect, it, vi } from 'vitest'
import { http } from '@/lib/http'
import { spreadsheetMergeApi, type SpreadsheetMergeRequest } from '@/api/spreadsheetMerge'

vi.mock('@/lib/http', () => ({ http: { post: vi.fn(), get: vi.fn() } }))
afterEach(() => vi.clearAllMocks())
const request: SpreadsheetMergeRequest = {
  primary: { name: '主表', headers: ['货号', '产品名称', '备注'], rows: [], header_row: 3 },
  secondary: { name: '副表', headers: ['货号', '名称', '客户'], rows: [['001', null, '客户甲']], header_row: 5 },
  mapping: [{ source: 0, target: 0 }, { source: 1, target: 1 }], key_columns: [0, 1],
  remarks_column: 2, extra_columns_to_remarks: [2], resolutions: { 'p0:s0:c1': 'secondary' }, profile: 'carton-packaging', batch_size: 500,
  template_id: 'carton-packaging', factory_id: 'huaxing',
}

describe('spreadsheet merge API contract', () => {
  it('inspects multipart XLSX with an explicit preset and cancellation signal', async () => {
    const signal = new AbortController().signal
    const file = new File(['data'], '客户.xlsx')
    vi.mocked(http.post).mockResolvedValue({ data: { filename: file.name, sheets: [], warnings: [] } })
    await spreadsheetMergeApi.inspect(file, 'carton-packaging-source', signal)
    const [path, body, config] = vi.mocked(http.post).mock.calls[0]!
    expect(path).toBe('/tools/spreadsheet-merge/inspect')
    expect((body as FormData).get('file')).toBe(file)
    expect((body as FormData).get('preset')).toBe('carton-packaging-source')
    expect(config).toMatchObject({ signal, headers: { 'Content-Type': undefined }, timeout: 180_000 })
  })
  it('sends the complete observed table, matching keys, extra fields and conflict decisions without adding defaults', async () => {
    vi.mocked(http.post).mockResolvedValue({ data: { rows: [] } })
    const signal = new AbortController().signal
    await spreadsheetMergeApi.preview(request, signal)
    expect(http.post).toHaveBeenCalledWith('/tools/spreadsheet-merge/preview', request, { timeout: 180_000, signal })
    expect(request.secondary.rows[0]?.[1]).toBeNull()
    expect(request.secondary.rows[0]?.[0]).toBe('001')
  })
  it('returns the server ZIP name and uses the same request for export', async () => {
    const blob = new Blob(['data'])
    vi.mocked(http.post).mockResolvedValue({ data: blob, headers: { 'content-disposition': "attachment; filename*=UTF-8''%E5%BE%85%E8%A1%A5%E7%89%88.zip" } })
    expect(await spreadsheetMergeApi.export(request)).toEqual({ blob, filename: '待补版.zip' })
    expect(http.post).toHaveBeenCalledWith('/tools/spreadsheet-merge/export', request, expect.objectContaining({ responseType: 'blob' }))
  })
  it('shows the server explanation for rejected binary exports', async () => {
    const blob = new Blob(['{"detail":"仍有冲突未决定"}'], { type: 'application/json' })
    Object.defineProperty(blob, 'text', { value: async () => '{"detail":"仍有冲突未决定"}' })
    vi.mocked(http.post).mockRejectedValue({ isAxiosError: true, response: { data: blob } })
    await expect(spreadsheetMergeApi.export(request)).rejects.toThrow('仍有冲突未决定')
  })
  it('loads available template contracts instead of hardcoding business columns', async () => {
    vi.mocked(http.get).mockResolvedValue({ data: [{ id: 'carton-packaging', headers: request.primary.headers }] })
    expect(await spreadsheetMergeApi.templates('huaxing')).toEqual([{ id: 'carton-packaging', headers: request.primary.headers }])
    expect(http.get).toHaveBeenCalledWith('/tools/spreadsheet-merge/templates', { signal: undefined, params: { factory_id: 'huaxing' } })
  })
  it('includes the factory for downloading an authorized original template', async () => {
    const blob = new Blob(['data'])
    vi.mocked(http.get).mockResolvedValue({ data: blob, headers: { 'content-disposition': 'attachment; filename="history-template.xlsx"' } })
    expect(await spreadsheetMergeApi.template('carton-history-orders', 'huaxing')).toEqual({ blob, filename: 'history-template.xlsx' })
    expect(http.get).toHaveBeenCalledWith('/tools/spreadsheet-merge/templates/carton-history-orders', expect.objectContaining({ params: { factory_id: 'huaxing' }, responseType: 'blob' }))
  })
})
