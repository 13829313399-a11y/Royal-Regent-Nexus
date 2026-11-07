// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import * as XLSX from 'xlsx'
import App from '../App'

const runtime = vi.hoisted(() => ({ generate: vi.fn(), compute: vi.fn() }))
const parsed = (customer: string) => ({
  invoices: [{ customer, label: customer, month: 1, ym: '2026-01', invNo: '123', kind: 'trade_noded' }],
  skipped: [], warnings: [], segments: [],
  summary: { cancelled: 0, emptySheets: [], customers: { [customer]: { count: 1, months: { 1: 1 } } } },
})
vi.mock('../lib/huakangA.js', () => ({
  HKA_CUSTOMERS: { 'Green Toys': { tpl: '/hka-tpl/a.xlsx', file: 'a.xlsx' } },
  parseHkaRecords: () => parsed('Green Toys'), generateHkaFiles: (...args: unknown[]) => runtime.generate(...args),
}))
vi.mock('../lib/huakangB.js', () => ({
  parseHkbRecord: () => parsed('INDEX'),
  summarizeHkb: () => [{ label: 'INDEX', count: 1, kinds: [] }], findHkbDuplicates: () => [],
  generateHkbFiles: (...args: unknown[]) => runtime.generate(...args),
}))
vi.mock('../lib/huakangD.js', () => ({
  HKD_CUSTOMERS: { MAXX: { tpl: 'maxx', currency: 'USD', rate: 1 } },
  HKD_TPLS: { maxx: { file: '/hkd-tpl/d.xlsx' } },
  parseHkdRecords: () => parsed('MAXX'), generateHkdFiles: (...args: unknown[]) => runtime.generate(...args),
}))
vi.mock('../lib/hkbLedger.js', () => ({
  HKB_LEDGER_SHEETS: ['华登（贸易）'], scanLedgerMonths: () => [1],
  computeHkbLedgerFills: (...args: unknown[]) => runtime.compute(...args), fillHkbLedgerWorkbook: vi.fn(),
}))

let changed: Record<string, unknown>
let finish: (files: unknown[]) => void
const files = [{ label: 'Result', fileName: 'private-result.xlsx', buffer: new ArrayBuffer(8), sheetCount: 1, invoices: [] }]
beforeEach(() => {
  changed = {}
  runtime.compute.mockReset()
  runtime.generate.mockReset().mockImplementation(() => new Promise(resolve => { finish = resolve }))
  vi.spyOn(console, 'error').mockImplementation(() => {})
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (!url.includes('/context?')) return new Response(new ArrayBuffer(8))
    const factory = new URL(url, 'http://localhost').searchParams.get('factory_id')
    return new Response(JSON.stringify({ factory_id: factory, user_id: 'user-a', employment_epoch: 1,
      templates: { '/hka-tpl/a.xlsx': 'a', '/hkb-tpl/华康B贸易.xlsx': 'b1',
        '/hkb-tpl/华康B国际.xlsx': 'b2', '/hkd-tpl/d.xlsx': 'd' }, ...changed }))
  }))
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

async function upload(label: string) {
  const book = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(book, XLSX.utils.aoa_to_sheet([['test']]), '华登（贸易）')
  const buffer = XLSX.write(book, { bookType: 'xlsx', type: 'array' })
  const file = new File([buffer], '其他客.xlsx')
  file.arrayBuffer = async () => buffer
  await act(async () => fireEvent.change(screen.getByLabelText(label), { target: { files: [file] } }))
}
async function start(factory: string) {
  window.history.replaceState({}, '', '?factory_id=' + factory)
  render(<App />)
  const label = factory === 'huakang-b' ? '发票原件记录上传' : '记录文件上传'
  await waitFor(() => expect(screen.getByLabelText(label)).toBeTruthy())
  await upload(label)
  if (factory !== 'huakang-b') fireEvent.click(screen.getByRole('button', { name: '解析预览' }))
}

// No private workbooks: defer the calculation boundary and exercise real session checks.
describe('invoice results stay with their originating account', () => {
  for (const factory of ['huakang-a', 'huakang-b', 'huakang-d']) {
    it.each([{ user_id: 'user-b' }, { employment_epoch: 2 }])(`${factory} rejects late generation after %j`, async identity => {
      await start(factory)
      fireEvent.click(screen.getByRole('button', { name: /生成发票工作簿/ }))
      await waitFor(() => expect(runtime.generate).toHaveBeenCalledTimes(1))
      changed = identity
      await act(async () => finish(files))
      await waitFor(() => expect(screen.getByRole('status').textContent).toContain('会话或权限已失效'))
      expect(screen.queryByText('private-result.xlsx')).toBeNull()
      expect(screen.queryByRole('button', { name: '整包下载（zip）' })).toBeNull()
    })
  }
  it('keeps a completed generation when the original identity is still authorized', async () => {
    await start('huakang-b')
    fireEvent.click(screen.getByRole('button', { name: /生成发票工作簿/ }))
    await waitFor(() => expect(runtime.generate).toHaveBeenCalledTimes(1))
    await act(async () => finish(files))
    await waitFor(() => expect(screen.getByText('private-result.xlsx')).toBeTruthy())
  })
  it.each([{ user_id: 'user-b' }, { employment_epoch: 2 }])('B rejects late metaOnly data before filling or caching after %j', async identity => {
    await start('huakang-b')
    await upload('台账工作簿上传')
    fireEvent.click(screen.getByRole('button', { name: '填充台账右侧' }))
    await waitFor(() => expect(runtime.generate).toHaveBeenCalledTimes(1))
    expect(runtime.generate.mock.calls[0]?.[2]).toEqual({ metaOnly: true })
    changed = identity
    await act(async () => finish(files))
    await waitFor(() => expect(screen.getByRole('status').textContent).toContain('会话或权限已失效'))
    expect(runtime.compute).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: /下载已填充/ })).toBeNull()
  })
})
