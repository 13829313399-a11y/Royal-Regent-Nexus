import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DOMWrapper, flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import Dialog from '../LegacyStockPreviewDialog.vue'
import type { LegacyStockPreview, LegacyStockRow } from '@/api/fabricLegacyStock'

const api = vi.hoisted(() => ({ preview: vi.fn() }))
vi.mock('@/api/fabricLegacyStock', () => ({ fabricLegacyStockApi: api }))
let wrapper: VueWrapper | undefined
const firstRow: LegacyStockRow = { row_number: 4, quantity: '12.5', raw_quantity: '12.5', duplicate_of: null,
  raw_unit: 'PCS', unit: 'PCS', unit_basis: '只归并显示，不换算数量。', conversion_only: false,
  new_item_code: '00012', item_code: 'OLD-12', item_name: '白布', location: '一仓／A01', supplier: '测试厂' }
const preview: LegacyStockPreview = {
  filename: '旧库存.xlsx', sheet: '物料', sheet_rows: 5, header_row: 3, quantity_key: 'current_quantity', quantity_column: '本月结存',
  field_mapping: { item_name: { header: '物料名称规格', column: 'V' }, current_quantity: { header: '本月结存', column: 'AA' } },
  summary: { total_rows: 2, valid_rows: 1, zero_rows: 0, missing_qty: 0, invalid_qty: 0, missing_unit: 0, duplicate_rows: 0, duplicate_groups: 0, conversion_only_rows: 0 },
  matching: { material: { matched: 1, unmatched: 1, ambiguous: 0 }, location: { matched: 2, unmatched: 0, ambiguous: 0 }, supplier: { matched: 2, unmatched: 0, ambiguous: 0 } },
  totals: { 码: '12.5' }, issue_counts: { UNMATCHED_MATERIAL: 1 }, problem_count: 1, problems_truncated: false, posted: false, read_only: true,
  rows: [], unit_aliases: [{ raw: '码', canonical: '码', rows: 2, conversion_only: false }],
  conversion_totals: {}, unique_totals: { 码: '12.5' }, matched_unique_totals: { 码: '0' }, duplicate_groups: [], duplicate_groups_truncated: false,
  quantity_basis: '公式只读文件缓存，不计算。', totals_basis: '含重复及未匹配，不能直接作为系统库存。',
  unique_totals_basis: '每组仅计首行，未合并或删除任何原表行。', matched_unique_totals_basis: '物料、仓位、供应商均唯一匹配且已启用，数量及单位有效。',
  conversion_totals_basis: '转算专用数量单独累计，不计入三类实物合计。',
  problems: [{ row_number: 5, raw: { item_name: '白布', current_quantity: '=Z5+AB5-AC5' }, values: { item_name: '白布', current_quantity: '12.5', unit: '码', location: '旧位', supplier: '测试厂' }, quantity: '12.5',
    raw_unit: '码', unit: '码', unit_basis: '保留原单位，不换算数量。', conversion_only: false,
    formula_fields: ['current_quantity'], unresolved_formulas: [], issues: ['UNMATCHED_MATERIAL'], suggestions: ['核对新物料编号及旧编码。'], matches: { material: [], location: ['L1'], supplier: ['S1'] }, duplicate_of: null }],
}
beforeEach(() => { vi.clearAllMocks(); api.preview.mockResolvedValue(structuredClone(preview)) })
afterEach(() => { wrapper?.unmount(); wrapper = undefined; document.body.innerHTML = ''; vi.restoreAllMocks() })
async function open() { wrapper = mount(Dialog, { attachTo: document.body }); await flushPromises(); return new DOMWrapper(document.body) }
async function choose(body: DOMWrapper<Element>, file = new File(['sample'], '旧库存.xlsx')) {
  const input = body.get('[aria-label="旧库存表文件"]')
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  await input.trigger('change')
}
function action(body: DOMWrapper<Element>) { return body.findAll('button').find(button => button.text() === '开始预检')! }

describe('legacy stock read-only preview dialog', () => {
  it('uploads once and renders summary, matching and raw problem evidence without posting actions', async () => {
    const body = await open()
    expect(body.get('[role="dialog"]').text()).toContain('仅预检，不入账')
    expect(action(body).attributes('disabled')).toBeDefined()
    await choose(body); await action(body).trigger('click'); await flushPromises()
    expect(api.preview).toHaveBeenCalledWith(expect.any(File), expect.any(AbortSignal))
    expect(body.text()).toContain('表头第 3 行')
    expect(body.text()).toContain('未匹配 1')
    expect(body.text()).toContain('12.5')
    expect(body.text()).toContain('UNMATCHED_MATERIAL')
    expect(body.text()).toContain('=Z5+AB5-AC5')
    expect(body.findAll('button').map(button => button.text())).toEqual(['关闭预检', '开始预检'])
  })
  it('separates unit aliases, all duplicate rows, three physical totals and conversion totals', async () => {
    const duplicateRows = [firstRow, { ...firstRow, row_number: 6, duplicate_of: 4 }]
    api.preview.mockResolvedValueOnce({ ...structuredClone(preview),
      summary: { ...preview.summary, total_rows: 4, duplicate_rows: 1, duplicate_groups: 1, conversion_only_rows: 1 },
      unit_aliases: [{ raw: 'PCS', canonical: 'PCS', rows: 2, conversion_only: false }, { raw: 'Pcs', canonical: 'PCS', rows: 1, conversion_only: false },
        { raw: '千克(转算专用)', canonical: 'KG（转算专用）', rows: 1, conversion_only: true }],
      totals: { PCS: '32.5' }, unique_totals: { PCS: '20' }, matched_unique_totals: { PCS: '12.5' }, conversion_totals: { 'KG（转算专用）': '3' },
      duplicate_groups: [{ key: 'row-4', rows: duplicateRows, count: 2, rows_truncated: false }],
    })
    const body = await open(); await choose(body); await action(body).trigger('click'); await flushPromises()
    const aliases = body.get('[aria-label="单位归并"]')
    expect(aliases.findAll('tbody tr')).toHaveLength(3)
    expect(aliases.text()).toContain('PcsPCS1')
    expect(aliases.text()).toContain('是 · 不计实物合计')
    expect(body.text()).toContain('只归并显示，不换算数量')
    expect(body.get('[aria-label="原表合计"]').text()).toContain('32.5')
    expect(body.get('[aria-label="原表合计"]').text()).toContain('不能直接作为系统库存')
    expect(body.get('[aria-label="非重复合计"]').text()).toContain('20')
    expect(body.get('[aria-label="已匹配且非重复合计"]').text()).toContain('12.5')
    for (const label of ['原表合计', '非重复合计', '已匹配且非重复合计']) expect(body.get(`[aria-label="${label}"]`).text()).not.toContain('KG（转算专用）')
    expect(body.get('[aria-label="转算专用数量"]').text()).toContain('3 KG（转算专用）')
    const duplicates = body.get('[aria-label="重复行待确认"]')
    expect(duplicates.text()).toContain('系统不自动合并，入账前必须人工确认')
    expect(duplicates.findAll('tbody tr').map(row => row.findAll('td')[0]!.text())).toEqual(['4组内首行', '6重复第 4 行'])
    expect(duplicates.text()).toContain('测试厂')
    expect(body.get('.legacy-stock-summary').text()).toContain('重复组数1')
    expect(body.get('.legacy-stock-summary').text()).toContain('转算专用行数1')
    expect(body.findAll('button').map(button => button.text())).toEqual(['关闭预检', '开始预检'])
  })
  it('shows duplicate truncation separately from the problem-row cap and keeps no-match totals explicit', async () => {
    api.preview.mockResolvedValueOnce({ ...structuredClone(preview),
      summary: { ...preview.summary, total_rows: 1001, duplicate_groups: 1, duplicate_rows: 1000 },
      duplicate_groups_truncated: true,
      duplicate_groups: [{ key: 'row-4', rows: [firstRow, { ...firstRow, row_number: 5, duplicate_of: 4 }], count: 1001, rows_truncated: true }],
      matched_unique_totals: {},
    })
    const body = await open(); await choose(body); await action(body).trigger('click'); await flushPromises()
    const duplicates = body.get('[aria-label="重复行待确认"]')
    expect(duplicates.text()).toContain('最多展示 200 组、1000 行')
    expect(duplicates.text()).toContain('本组仅展示 2 / 1001 行')
    expect(body.get('[aria-label="已匹配且非重复合计"]').text()).toContain('0（没有符合此口径的实物数量）')
  })
  it.each([403, 413, 422])('reports preview failure %s and permits another upload', async status => {
    api.preview.mockRejectedValueOnce({ isAxiosError: true, response: { status, data: { detail: '工作簿表头不匹配' } } })
    const body = await open(); await choose(body); await action(body).trigger('click'); await flushPromises()
    expect(body.get('[role="alert"]').text()).toContain(status === 403 ? '权限' : status === 413 ? '10 MiB' : '表头不匹配')
    expect(body.find('table').exists()).toBe(false)
    await choose(body)
    expect(body.find('[role="alert"]').exists()).toBe(false)
  })
  it('rejects oversized and non-xlsx files locally', async () => {
    const body = await open()
    await choose(body, new File(['sample'], '库存.xls'))
    expect(body.get('[role="alert"]').text()).toContain('.xlsx')
    const file = new File(['sample'], '库存.xlsx'); Object.defineProperty(file, 'size', { value: 10 * 1024 * 1024 + 1 })
    await choose(body, file)
    expect(body.get('[role="alert"]').text()).toContain('10 MiB')
    expect(action(body).attributes('disabled')).toBeDefined()
    expect(api.preview).not.toHaveBeenCalled()
  })
  it('discards late results when another file is chosen and clears everything when closed', async () => {
    let resolve!: (value: LegacyStockPreview) => void
    api.preview.mockImplementationOnce(() => new Promise(done => { resolve = done }))
    let body = await open(); await choose(body); await action(body).trigger('click')
    const signal = api.preview.mock.calls[0]![1] as AbortSignal
    await choose(body, new File(['next'], '新的.xlsx'))
    expect(signal.aborted).toBe(true)
    resolve(structuredClone(preview)); await flushPromises()
    expect(body.find('table').exists()).toBe(false)
    await action(body).trigger('click'); await flushPromises()
    expect(body.find('table').exists()).toBe(true)
    await body.findAll('button').find(button => button.text() === '关闭预检')!.trigger('click')
    expect(wrapper!.emitted('close')).toHaveLength(1)
    wrapper!.unmount(); wrapper = undefined
    body = await open()
    expect(action(body).attributes('disabled')).toBeDefined()
    expect(body.find('table').exists()).toBe(false)
    expect(body.text()).not.toContain('新的.xlsx')
  })
})
