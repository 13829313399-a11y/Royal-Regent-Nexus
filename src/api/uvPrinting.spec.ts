import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/http', () => ({
  http: { get: vi.fn(), post: vi.fn() },
}))

import { http } from '@/lib/http'
import { uvPrintingApi } from './uvPrinting'

const scope = { factory_id: 'huakang-a' as const }
const live = <T>(data: T) => ({
  data: {
    meta: { factory_id: 'huakang-a' as const, as_of: '2026-09-14T00:00:00Z', data_mode: 'live' as const, coverage: 'complete' as const, warnings: [] },
    data,
  },
})

const exportInput = {
  factory_id: 'huakang-a' as const,
  operation_id: 'export-1',
  expected_version: 0,
  kind: 'daily' as const,
  scope,
}

describe('正式 UV API 客户端', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('拒绝 sample 或别厂 meta，正式页面不能把它当 live 数据渲染', async () => {
    vi.mocked(http.get).mockResolvedValue({
      data: { meta: { factory_id: 'huakang-a', as_of: '2026-09-14T00:00:00Z', data_mode: 'sample', coverage: 'complete', warnings: [] }, data: {} },
    } as never)
    await expect(uvPrintingApi.summary(scope)).rejects.toMatchObject({ code: 'uv_factory_mismatch' })

    vi.mocked(http.get).mockResolvedValue({
      data: { meta: { factory_id: 'huaxing', as_of: '2026-09-14T00:00:00Z', data_mode: 'live', coverage: 'complete', warnings: [] }, data: {} },
    } as never)
    await expect(uvPrintingApi.summary(scope)).rejects.toMatchObject({ code: 'uv_factory_mismatch' })
  })

  it('下载使用一次同源 /api/uv-printing 地址，不让 Axios 再拼 /api', async () => {
    vi.mocked(http.post).mockResolvedValue(live({
      kind: 'daily', file_name: 'daily.csv', generated_at: '2026-09-14T00:00:00Z', row_count: 1, scope_label: '华康A',
      download_url: '/api/uv-printing/exports/daily?factory_id=huakang-a',
    }) as never)
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, blob: async () => new Blob(['a']) })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:test'), revokeObjectURL: vi.fn() }))
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

    await uvPrintingApi.exportReport(exportInput)

    expect(fetchMock).toHaveBeenCalledWith('/api/uv-printing/exports/daily?factory_id=huakang-a', { credentials: 'include' })
    expect(click).toHaveBeenCalledOnce()
  })

  it('拒绝跨域或不在该导出类型白名单内的下载地址', async () => {
    vi.mocked(http.post).mockResolvedValue(live({
      kind: 'daily', file_name: 'daily.csv', generated_at: '2026-09-14T00:00:00Z', row_count: 1, scope_label: '华康A',
      download_url: 'https://example.invalid/api/uv-printing/exports/daily',
    }) as never)
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    await expect(uvPrintingApi.exportReport(exportInput)).rejects.toThrow('无效下载地址')
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
