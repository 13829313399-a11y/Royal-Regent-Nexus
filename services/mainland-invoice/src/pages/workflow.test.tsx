// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import JSZip from 'jszip'
import * as XLSX from 'xlsx'
import App from '../App'
import { HKA_CUSTOMERS } from '../lib/huakangA.js'
import { HKD_TPLS } from '../lib/huakangD.js'

// Optional private acceptance fixtures: never copy records/templates into Git.
const source = process.env.INVOICE_ACCEPTANCE_SOURCE
function browserBuffer(bytes: Uint8Array) {
  const buffer = new window.ArrayBuffer(bytes.byteLength)
  new window.Uint8Array(buffer).set(bytes)
  return buffer
}
const cases = [
  {
    factory: 'huakang-a', customer: 'Green Toys', label: '记录文件上传',
    files: ['华康A/发票记录原件/2026年华康A发票记录（ZURU ）.xlsx', '华康A/发票记录原件/2026年华康A发票记录---其他客.xls'],
    paths: Object.values(HKA_CUSTOMERS).map(x => x.tpl),
  },
  {
    factory: 'huakang-b', customer: 'INDEX', label: '发票原件记录上传',
    files: ['华康B_副本/发票原件/发票原件记录.xls'],
    paths: ['/hkb-tpl/华康B贸易.xlsx', '/hkb-tpl/华康B国际.xlsx'],
  },
  {
    factory: 'huakang-d', customer: 'MAXX', label: '记录文件上传',
    files: ['华康D/发票记录原件/原件记录数据.et'],
    paths: Object.values(HKD_TPLS).map(x => x.file),
  },
]
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })
describe.skipIf(!source)('private original files through online UI', () => {
  for (const item of cases) it(item.factory + ' uploads, generates and downloads a ZIP', async () => {
    window.history.replaceState({}, '', '/mainland-invoice/?factory_id=' + item.factory)
    const templates = Object.fromEntries(item.paths.map(p => [p, p]))
    vi.stubGlobal('fetch', vi.fn(async (value: string) => {
      const url = new URL(value, 'http://localhost')
      expect(url.searchParams.get('factory_id')).toBe(item.factory)
      if (url.pathname.endsWith('/context')) {
        return new Response(JSON.stringify({ factory_id: item.factory, user_id: 'user-a', employment_epoch: 1, templates }))
      }
      const path = decodeURIComponent(url.pathname.split('/').at(-1)!)
      expect(item.paths).toContain(path)
      const bytes = readFileSync(join(source!, 'public', path))
      return { ok: true, arrayBuffer: async () => browserBuffer(bytes) }
    }))
    const clicked = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    let savedBlob: Blob | undefined
    URL.createObjectURL = vi.fn((blob: Blob) => { savedBlob = blob; return 'blob:test' })
    URL.revokeObjectURL = vi.fn()
    render(<App />)
    await waitFor(() => expect(screen.getByLabelText(item.label)).toBeTruthy())
    const files = item.files.map(path => {
      const bytes = readFileSync(join(source!, '..', '各厂区大陆发票数据', path))
      const file = new File([bytes], path.split('/').at(-1)!)
      file.arrayBuffer = async () => browserBuffer(bytes)
      return file
    })
    await act(async () => fireEvent.change(screen.getByLabelText(item.label), { target: { files } }))
    if (item.factory !== 'huakang-b') {
      await act(async () => fireEvent.click(screen.getByRole('button', { name: '解析预览' })))
    }
    // Keep acceptance bounded: select one customer after parsing the full record.
    for (const box of screen.getAllByRole('checkbox') as HTMLInputElement[]) {
      const label = box.closest('tr')?.textContent?.replaceAll(' ', '') ?? ''
      if (box.checked && label.includes('发票.xlsx') && !label.includes(item.customer.replaceAll(' ', ''))) {
        fireEvent.click(box)
      }
    }
    await act(async () => fireEvent.click(screen.getByRole('button', { name: /生成发票工作簿/ })))
    await waitFor(() => expect(screen.getByRole('button', { name: '整包下载（zip）' })).toBeTruthy(), { timeout: 120000 })
    await act(async () => fireEvent.click(screen.getByRole('button', { name: '整包下载（zip）' })))
    await waitFor(() => expect(clicked).toHaveBeenCalled(), { timeout: 120000 })
    expect(savedBlob).toBeTruthy()
    // Read the jsdom Blob without modifying any workbook.
    const reader = new FileReader()
    const buffer = await new Promise<ArrayBuffer>((resolve, reject) => {
      reader.onload = () => resolve(reader.result as ArrayBuffer)
      reader.onerror = reject
      reader.readAsArrayBuffer(savedBlob!)
    })
    const zip = await JSZip.loadAsync(buffer)
    expect(Object.keys(zip.files).some(name => name.endsWith('.xlsx'))).toBe(true)
    if (item.factory === 'huakang-b') {
      // B source UI update: selecting a worksheet must limit the fill operation.
      const book = XLSX.utils.book_new()
      for (const name of ['华登（贸易）', 'USC（国际）', '华登（实业）']) {
        XLSX.utils.book_append_sheet(book, XLSX.utils.aoa_to_sheet([
          ['2026年1月份'], [46026, '英特', 'TEST-1', 100],
        ]), name)
      }
      const bytes = new Uint8Array(XLSX.write(book, { bookType: 'xlsx', type: 'array' }))
      const file = new File([bytes], '本地台账.xlsx')
      file.arrayBuffer = async () => browserBuffer(bytes)
      await act(async () => fireEvent.change(screen.getByLabelText('台账工作簿上传'), { target: { files: [file] } }))
      fireEvent.click(screen.getByLabelText('华登（贸易）'))
      fireEvent.click(screen.getByLabelText('华登（实业）'))
      await act(async () => fireEvent.click(screen.getByRole('button', { name: '填充台账右侧' })))
      await waitFor(() => expect(screen.getByRole('button', { name: '下载已填充台账（1 行）' })).toBeTruthy(), { timeout: 120000 })
    }
  }, 180000)
})
