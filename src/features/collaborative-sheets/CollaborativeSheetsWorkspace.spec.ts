import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import Workspace from './CollaborativeSheetsWorkspace.vue'
import { collaborativeSheetsApi as api, type FillTaskDetail } from '@/api/collaborativeSheets'
import { canFill, clipboardRows, columnName, parseInput, rangeBounds } from './grid'
import { canChangeFactory } from '@/lib/factoryChangeGuard'

vi.mock('vue-router', () => ({ onBeforeRouteLeave: vi.fn(), onBeforeRouteUpdate: vi.fn() }))
const example = (): FillTaskDetail => ({
  id: 't1', title: '协同填写试验', original_name: '试验.xls', format: 'xls', factory_id: 'huaxing',
  owner_user_id: 'u1', owner_name: '上传人', status: 'open', revision: 1, is_owner: true,
  created_at: '2026-10-09T01:00:00Z', updated_at: '2026-10-09T01:00:00Z',
  grants: [{ principal_type: 'user', principal_id: 'u2', sheet: 0, range: 'B2:C3' }],
  editable_ranges: [{ sheet: 0, range: 'B2:C3' }], submissions: [], activity: [],
  workbook: { warnings: ['公式结果在下载后由 Excel 重新计算。'], sheets: [{
    index: 0, name: '货款', rows: 3, columns: 3, merges: ['A1:C1'], row_heights: {}, column_widths: {},
    cells: [
      { address: 'A1', row: 0, column: 0, value: '月度货款', display: '月度货款', formula: false, style: {} },
      { address: 'B2', row: 1, column: 1, value: 10, display: '10.00', formula: false, style: {} },
      { address: 'C2', row: 1, column: 2, value: 20, display: '20.00', formula: true, style: {} },
    ],
  }] },
})
let wrapper: VueWrapper | undefined
const button = (text: string) => wrapper!.findAll('button').find(b => b.text().includes(text))!
async function render() {
  wrapper = mount(Workspace, { props: { factoryId: 'huaxing' }, global: { stubs: {
    UniverFillGrid: { template: '<div />', methods: { finishEditing: async () => true } },
  } } })
  await flushPromises()
  await button('协同填写试验').trigger('click')
  await flushPromises()
  // These existing DOM-grid regressions exercise the available original-editor fallback.
  await button('使用原版编辑器').trigger('click')
  await flushPromises()
}
beforeEach(() => {
  vi.spyOn(api, 'list').mockResolvedValue({ items: [example()] })
  vi.spyOn(api, 'recipients').mockResolvedValue({ users: [{ id: 'u2', display_name: '填写人', department: 'sales-business' }], departments: [{ id: 'sales-business', name: '营业部' }] })
  vi.spyOn(api, 'detail').mockResolvedValue(example())
  vi.spyOn(api, 'participants').mockResolvedValue({ id: 't1', revision: 1, status: 'open', participants: [] })
  vi.spyOn(api, 'save').mockImplementation(async (_factory, task, changes) => {
    const result = example(); result.revision = task.revision + 1
    for (const c of changes) {
      const cell = result.workbook.sheets[c.sheet]!.cells.find(x => x.address === c.address)
      if (cell) { cell.value = c.value; cell.display = String(c.value) }
    }
    return result
  })
  vi.spyOn(api, 'grants').mockResolvedValue(example())
  vi.spyOn(api, 'state').mockResolvedValue({ ...example(), status: 'closed' })
  vi.spyOn(api, 'submit').mockResolvedValue(example())
  vi.spyOn(window, 'confirm').mockReturnValue(true)
})
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.restoreAllMocks() })

describe('协同填表', () => {
  it('shows the upload limit, rejects an oversized selection, and allows a replacement', async () => {
    const create = vi.spyOn(api, 'create').mockResolvedValue(example())
    await render(); await button('上传表格').trigger('click')
    expect(wrapper!.get('#cs-upload-size').text()).toContain('100 MB')
    const input = wrapper!.get('input[type="file"]')
    const oversized = new File(['sample'], 'oversize.xlsx')
    Object.defineProperty(oversized, 'size', { value: 100 * 1024 * 1024 + 1 })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [oversized] })
    await input.trigger('change')
    expect(wrapper!.get('[role="alert"]').text()).toContain('工作簿不能超过 100 MB')
    expect(button('上传并设置填写范围').attributes('disabled')).toBeDefined()
    await wrapper!.get('.cs-upload-form').trigger('submit'); await flushPromises()
    expect(create).not.toHaveBeenCalled()
    const replacement = new File(['sample'], 'replacement.xlsx')
    Object.defineProperty(replacement, 'size', { value: 100 * 1024 * 1024 })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [replacement] })
    await input.trigger('change')
    expect(wrapper!.find('[role="alert"]').exists()).toBe(false)
    await wrapper!.get('.cs-upload-form').trigger('submit'); await flushPromises()
    expect(create).toHaveBeenCalledWith('huaxing', 'replacement', replacement)
  })

  it('previews multiple departments and saves their shared range once per department', async () => {
    vi.mocked(api.recipients).mockResolvedValue({ users: [
      { id: 'u2', display_name: '业务填写人', department: 'sales-business' },
      { id: 'u3', display_name: '工程填写人', department: 'engineering' },
      { id: 'u4', display_name: '未选部门人员', department: 'qc' },
    ], departments: [{ id: 'sales-business', name: '业务部' }, { id: 'engineering', name: '工程部' }, { id: 'qc', name: '品质部' }] })
    await render(); await button('分配填写').trigger('click')
    await wrapper!.get('input[value="sales-business"]').setValue(true)
    await wrapper!.get('input[value="engineering"]').setValue(true)
    expect(wrapper!.get('.cs-member-preview').text()).toContain('2 人')
    expect(wrapper!.get('.cs-member-preview').text()).toContain('工程填写人')
    expect(wrapper!.get('.cs-member-preview').text()).not.toContain('未选部门人员')
    await wrapper!.get('input[aria-label="填写范围"]').setValue('B3')
    await button('添加').trigger('click')
    expect(wrapper!.findAll('.cs-grants li')).toHaveLength(3)
    await wrapper!.get('input[aria-label="填写范围"]').setValue('B3')
    await button('添加').trigger('click')
    expect(wrapper!.findAll('.cs-grants li')).toHaveLength(3)
    await button('保存分配设置').trigger('click'); await flushPromises()
    expect(api.grants).toHaveBeenCalledWith('huaxing', expect.anything(), [example().grants[0],
      { principal_type: 'department', principal_id: 'sales-business', sheet: 0, range: 'B3' },
      { principal_type: 'department', principal_id: 'engineering', sheet: 0, range: 'B3' },
    ])
  })
  it('clears department selection when switching assignment type and refuses an empty selection', async () => {
    await render(); await button('分配填写').trigger('click')
    const department = wrapper!.get('input[value="sales-business"]')
    await department.setValue(true); await department.setValue(false)
    expect(wrapper!.find('.cs-member-preview').exists()).toBe(false)
    await wrapper!.get('input[aria-label="填写范围"]').setValue('B3')
    await button('添加').trigger('click')
    expect(wrapper!.findAll('.cs-grants li')).toHaveLength(1)
    await department.setValue(true)
    const mode = wrapper!.findAll('select').find(s => s.find('option[value="department"]').exists())!
    await mode.setValue('user')
    await wrapper!.findAll('select').find(s => s.find('option[value="u2"]').exists())!.setValue('u2')
    await button('添加').trigger('click')
    await mode.setValue('department')
    expect(wrapper!.get('input[value="sales-business"]').element).toHaveProperty('checked', false)
    expect(wrapper!.find('.cs-member-preview').exists()).toBe(false)
    await button('保存分配设置').trigger('click'); await flushPromises()
    expect(api.grants).toHaveBeenCalledWith('huaxing', expect.anything(), [example().grants[0], { principal_type: 'user', principal_id: 'u2', sheet: 0, range: 'B3' }])
  })
  it('rejects a multi-department batch atomically when it exceeds the assignment limit', async () => {
    const detail = example()
    detail.grants = Array.from({ length: 199 }, (_, i) => ({ principal_type: 'user', principal_id: `existing-${i}`, sheet: 0, range: 'B2' }))
    vi.mocked(api.detail).mockResolvedValue(detail)
    vi.mocked(api.recipients).mockResolvedValue({ users: [], departments: [{ id: 'sales-business', name: '业务部' }, { id: 'engineering', name: '工程部' }] })
    await render(); await button('分配填写').trigger('click')
    await wrapper!.get('input[value="sales-business"]').setValue(true)
    await wrapper!.get('input[value="engineering"]').setValue(true)
    await wrapper!.get('input[aria-label="填写范围"]').setValue('B3')
    await button('添加').trigger('click')
    expect(wrapper!.text()).toContain('本次选择尚未添加')
    expect(wrapper!.findAll('.cs-grants li')).toHaveLength(199)
    expect(button('保存分配设置').attributes('disabled')).toBeDefined()
  })
  it('lists every assigned account with a text and color status, including people with no submissions', async () => {
    const detail = example()
    detail.participants = ['not_started', 'in_progress', 'completed', 'needs_confirmation'].map((status, i) => ({
      user_id: `member${i}`, display_name: `业务员${i}`, department: 'sales-business',
      status: status as 'not_started' | 'in_progress' | 'completed' | 'needs_confirmation', last_saved_at: null, submitted_at: null,
    }))
    vi.mocked(api.detail).mockResolvedValue(detail)
    await render()
    expect(wrapper!.findAll('[data-participant]')).toHaveLength(4)
    expect(wrapper!.get('.cs-person-not_started').text()).toContain('未填写')
    expect(wrapper!.get('.cs-person-completed').text()).toContain('已完成')
    expect(wrapper!.text()).toContain('1 / 4 人已完成')
  })
  it('refreshes the roster without changing the revision or unsaved cell input', async () => {
    await render()
    await wrapper!.get('[data-cell=B2]').trigger('dblclick')
    await wrapper!.get('textarea[aria-label="编辑 B2"]').setValue('77')
    vi.mocked(api.participants).mockResolvedValue({ id: 't1', revision: 9, status: 'open', participants: [{ user_id: 'u2', display_name: '填写人', department: 'sales-business', status: 'completed', last_saved_at: null, submitted_at: '2026-10-09T01:00:00Z' }] })
    await button('刷新人员状态').trigger('click'); await flushPromises()
    expect(wrapper!.get('textarea[aria-label="编辑 B2"]').element).toHaveProperty('value', '77')
    expect(wrapper!.text()).toContain('表格已有新版本')
    await button('保存填写').trigger('click'); await flushPromises()
    expect(api.save).toHaveBeenCalledWith('huaxing', expect.objectContaining({ revision: 1 }), [{ sheet: 0, address: 'B2', value: 77 }])
  })
  it('edits inside a cell and commits with Enter before moving down', async () => {
    await render()
    await wrapper!.get('[data-cell=B2]').trigger('dblclick')
    await wrapper!.get('textarea[aria-label="编辑 B2"]').setValue('12.5%')
    await wrapper!.get('textarea[aria-label="编辑 B2"]').trigger('keydown', { key: 'Enter' })
    expect(wrapper!.get('[data-cell=B3]').classes()).toContain('cs-selected')
    expect(wrapper!.get('[data-cell=B2]').text()).toBe('0.125')
    await button('保存填写').trigger('click'); await flushPromises()
    expect(api.save).toHaveBeenCalledWith('huaxing', expect.anything(), [{ sheet: 0, address: 'B2', value: 0.125 }])
  })
  it('supports type-to-replace, Escape, F2 and Tab while keeping formula cells locked', async () => {
    await render()
    await wrapper!.get('[data-cell=B2]').trigger('keydown', { key: '8' })
    expect(wrapper!.get('textarea[aria-label="编辑 B2"]').element).toHaveProperty('value', '8')
    await wrapper!.get('textarea[aria-label="编辑 B2"]').trigger('keydown', { key: 'Escape' })
    expect(wrapper!.get('[data-cell=B2]').text()).toBe('10.00')
    expect(wrapper!.find('.cs-inline-input').exists()).toBe(false)
    await wrapper!.get('[data-cell=B2]').trigger('keydown', { key: 'F2' })
    await wrapper!.get('textarea[aria-label="编辑 B2"]').setValue('42')
    await wrapper!.get('textarea[aria-label="编辑 B2"]').trigger('keydown', { key: 'Tab' })
    expect(wrapper!.get('[data-cell=C2]').classes()).toContain('cs-selected')
    await wrapper!.get('[data-cell=C2]').trigger('dblclick')
    expect(wrapper!.find('.cs-inline-input').exists()).toBe(false)
    await wrapper!.get('[data-cell=C2]').trigger('keydown', { key: 'ArrowDown' })
    expect(wrapper!.get('[data-cell=C3]').classes()).toContain('cs-selected')
  })
  it('pastes rectangular values atomically and refuses ranges that cross a formula', async () => {
    await render()
    await wrapper!.get('[data-cell=B2]').trigger('paste', { clipboardData: { getData: () => '7\t8' } })
    expect(wrapper!.text()).toContain('本次粘贴未写入')
    expect(wrapper!.get('[data-cell=B2]').text()).toBe('10.00')
    await wrapper!.get('[data-cell=B3]').trigger('paste', { clipboardData: { getData: () => '00123\t25%\r\n' } })
    expect(wrapper!.get('[data-cell=B3]').text()).toBe('00123')
    expect(wrapper!.get('[data-cell=C3]').text()).toBe('0.25')
    await button('保存填写').trigger('click'); await flushPromises()
    expect(api.save).toHaveBeenCalledWith('huaxing', expect.anything(), [{ sheet: 0, address: 'B3', value: '00123' }, { sheet: 0, address: 'C3', value: 0.25 }])
  })
  it('does not end Chinese IME composition on Enter and supports Ctrl+S afterward', async () => {
    await render()
    await wrapper!.get('[data-cell=B2]').trigger('dblclick')
    const editor = wrapper!.get('textarea[aria-label="编辑 B2"]')
    await editor.trigger('compositionstart'); await editor.setValue('业务核对')
    await editor.trigger('keydown', { key: 'Enter', isComposing: true })
    expect(wrapper!.find('.cs-inline-input').exists()).toBe(true)
    await editor.trigger('compositionend')
    await editor.trigger('keydown', { key: 's', ctrlKey: true }); await flushPromises()
    expect(api.save).toHaveBeenCalledWith('huaxing', expect.anything(), [{ sheet: 0, address: 'B2', value: '业务核对' }])
  })
  it('copies raw numbers and quotes multiline text so pasting stays within one cell', async () => {
    const detail = example()
    detail.workbook.sheets[0]!.cells[1]!.value = 1234.5
    detail.workbook.sheets[0]!.cells[1]!.display = '1,234.50'
    vi.mocked(api.detail).mockResolvedValue(detail)
    await render()
    let copied = ''
    const clipboardData = { setData: (_type: string, text: string) => { copied = text }, getData: () => copied }
    await wrapper!.get('[data-cell=B2]').trigger('copy', { clipboardData })
    expect(copied).toBe('1234.5')
    await wrapper!.get('[data-cell=B3]').trigger('paste', { clipboardData })
    await wrapper!.get('[data-cell=B2]').trigger('dblclick')
    await wrapper!.get('textarea[aria-label="编辑 B2"]').setValue('第一行\n第二行\t备注')
    await wrapper!.get('textarea[aria-label="编辑 B2"]').trigger('keydown', { key: 'Enter' })
    await wrapper!.get('[data-cell=B2]').trigger('copy', { clipboardData })
    expect(copied).toBe('"第一行\n第二行\t备注"')
    await wrapper!.get('[data-cell=B3]').trigger('paste', { clipboardData })
    await button('保存填写').trigger('click'); await flushPromises()
    expect(api.save).toHaveBeenCalledWith('huaxing', expect.anything(), expect.arrayContaining([{ sheet: 0, address: 'B3', value: '第一行\n第二行\t备注' }]))
    expect(vi.mocked(api.save).mock.calls[0]![2]).toHaveLength(2)
  })
  it('starts Chinese type-to-replace with an empty cell editor', async () => {
    await render()
    await wrapper!.get('[data-cell=B2]').trigger('compositionstart')
    expect(wrapper!.get('textarea[aria-label="编辑 B2"]').element).toHaveProperty('value', '')
  })
  it.each(['123', 'TRUE', "'note", 'a"b'])('preserves copied string %s as one typed value', async value => {
    const detail = example(); detail.workbook.sheets[0]!.cells[1]!.value = value
    vi.mocked(api.detail).mockResolvedValue(detail)
    await render()
    const formats = new Map<string, string>()
    const clipboardData = { setData: (type: string, text: string) => formats.set(type, text), getData: (type: string) => formats.get(type) ?? '' }
    await wrapper!.get('[data-cell=B2]').trigger('copy', { clipboardData })
    await wrapper!.get('[data-cell=B3]').trigger('paste', { clipboardData })
    await button('保存填写').trigger('click'); await flushPromises()
    expect(api.save).toHaveBeenCalledWith('huaxing', expect.anything(), [{ sheet: 0, address: 'B3', value }])
  })
  it('inserts original quotes inside an active editor without TSV escaping', async () => {
    const detail = example(); detail.workbook.sheets[0]!.cells[1]!.value = 'a"b'
    vi.mocked(api.detail).mockResolvedValue(detail)
    await render()
    const formats = new Map<string, string>()
    const clipboardData = { setData: (type: string, text: string) => formats.set(type, text), getData: (type: string) => formats.get(type) ?? '' }
    await wrapper!.get('[data-cell=B2]').trigger('copy', { clipboardData })
    await wrapper!.get('[data-cell=B3]').trigger('dblclick')
    await wrapper!.get('textarea[aria-label="编辑 B3"]').trigger('paste', { clipboardData })
    expect(wrapper!.get('textarea[aria-label="编辑 B3"]').element).toHaveProperty('value', 'a"b')
    await button('保存填写').trigger('click'); await flushPromises()
    expect(api.save).toHaveBeenCalledWith('huaxing', expect.anything(), [{ sheet: 0, address: 'B3', value: 'a"b' }])
  })
  it('renders original merges and locks formula cells even within an assigned range', async () => {
    await render()
    expect(wrapper!.get('[data-cell=A1]').attributes('colspan')).toBe('3')
    await wrapper!.get('[data-cell=C2]').trigger('click')
    expect(wrapper!.text()).toContain('公式单元格，只读')
    expect(wrapper!.find('textarea').exists()).toBe(false)
    await wrapper!.get('[data-cell=B2]').trigger('click')
    expect(wrapper!.find('textarea').exists()).toBe(true)
  })
  it('saves the selected numeric value and revision instead of formatted display text', async () => {
    await render()
    await wrapper!.get('[data-cell=B2]').trigger('click')
    await wrapper!.get('textarea').setValue('123.45')
    await button('保存填写').trigger('click'); await flushPromises()
    expect(api.save).toHaveBeenCalledWith('huaxing', expect.objectContaining({ revision: 1 }), [{ sheet: 0, address: 'B2', value: 123.45 }])
    expect(wrapper!.text()).toContain('填写内容已保存到服务器')
  })
  it('keeps local values on a conflict, shows changed remote values, and requires another explicit save', async () => {
    vi.mocked(api.save).mockRejectedValueOnce({ response: { status: 409, data: { detail: '表格已更新' } } })
    await render()
    await wrapper!.get('[data-cell=B2]').trigger('click')
    await wrapper!.get('textarea').setValue('45')
    await button('保存填写').trigger('click'); await flushPromises()
    expect(wrapper!.text()).toContain('你的填写内容仍保留')
    const remote = example(); remote.revision = 2; remote.workbook.sheets[0]!.cells[1]!.value = 30
    vi.mocked(api.detail).mockResolvedValue(remote)
    await button('读取最新版本（保留我的填写）').trigger('click'); await flushPromises()
    expect(wrapper!.text()).toContain('服务器已改为“30”')
    expect(wrapper!.get('[data-cell=B2]').text()).toBe('45')
    expect(api.save).toHaveBeenCalledTimes(1)
    await button('保存填写').trigger('click'); await flushPromises()
    expect(api.save).toHaveBeenLastCalledWith('huaxing', expect.objectContaining({ revision: 2 }), [{ sheet: 0, address: 'B2', value: 45 }])
  })
  it('does not submit completion if saving fails', async () => {
    vi.mocked(api.save).mockRejectedValueOnce(new Error('连接失败'))
    await render()
    await wrapper!.get('[data-cell=B2]').trigger('click')
    await wrapper!.get('textarea').setValue('50')
    await button('我已填完').trigger('click'); await flushPromises()
    expect(api.submit).not.toHaveBeenCalled()
    expect(wrapper!.text()).toContain('连接失败')
  })
  it('does not grant group fallback access', async () => {
    wrapper = mount(Workspace, { props: { factoryId: 'group' } }); await flushPromises()
    expect(api.list).not.toHaveBeenCalled()
    expect(api.recipients).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('选择你所属的厂区')
  })
  it('requires confirmation to leave unsaved input', async () => {
    await render()
    await wrapper!.get('[data-cell=B2]').trigger('click')
    await wrapper!.get('textarea').setValue('88')
    vi.mocked(window.confirm).mockReturnValue(false)
    expect((wrapper!.vm as unknown as { confirmLeave(): boolean }).confirmLeave()).toBe(false)
    expect(canChangeFactory()).toBe(false)
    expect(window.confirm).toHaveBeenCalled()
    wrapper!.unmount(); wrapper = undefined
    expect(canChangeFactory()).toBe(true)
  })
  it('preserves pending assignments when cell edits are saved first', async () => {
    await render()
    await button('分配填写').trigger('click')
    await wrapper!.get('input[type="checkbox"][value="sales-business"]').setValue(true)
    await wrapper!.get('input[aria-label="填写范围"]').setValue('B3')
    await button('添加').trigger('click')
    await wrapper!.get('[data-cell=B2]').trigger('click')
    await wrapper!.get('textarea').setValue('99')
    expect(button('保存填写').attributes('disabled')).toBeUndefined()
    await button('保存填写').trigger('click'); await flushPromises()
    expect(wrapper!.text()).toContain('分配设置仍未保存')
    expect(wrapper!.get('.cs-grants').text()).toContain('B3')
    await button('保存分配设置').trigger('click'); await flushPromises()
    expect(api.grants).toHaveBeenCalledWith('huaxing', expect.objectContaining({ revision: 2 }), expect.arrayContaining([expect.objectContaining({ range: 'B3', principal_id: 'sales-business' })]))
  })
  it('preserves pending assignments and values through conflict refresh', async () => {
    vi.mocked(api.save).mockRejectedValueOnce({ response: { status: 409 } })
    await render()
    await button('分配填写').trigger('click')
    await wrapper!.get('input[type="checkbox"][value="sales-business"]').setValue(true)
    await wrapper!.get('input[aria-label="填写范围"]').setValue('B3')
    await button('添加').trigger('click')
    await wrapper!.get('[data-cell=B2]').trigger('click')
    await wrapper!.get('textarea').setValue('99')
    await button('保存填写').trigger('click'); await flushPromises()
    vi.mocked(api.detail).mockResolvedValue({ ...example(), revision: 2 })
    await button('读取最新版本（保留我的填写）').trigger('click'); await flushPromises()
    expect(wrapper!.get('.cs-grants').text()).toContain('B3')
    expect(wrapper!.get('[data-cell=B2]').text()).toBe('99')
    expect(wrapper!.text()).toContain('你的分配设置也已保留')
    await button('保存填写').trigger('click'); await flushPromises()
    await button('保存分配设置').trigger('click'); await flushPromises()
    expect(api.grants).toHaveBeenCalledWith('huaxing', expect.objectContaining({ revision: 3 }), expect.arrayContaining([expect.objectContaining({ range: 'B3' })]))
  })
})
describe('原表位置与输入类型', () => {
  it('reads quoted Excel clipboard rows and preserves multiline cell text', () => {
    expect(clipboardRows('"第一行\n第二行"\t"带""引号"\r\n')).toEqual([['第一行\n第二行', '带"引号']])
    expect(parseInput("'0123", 'auto')).toBe('0123')
    expect(parseInput('15%', 'auto')).toBe(0.15)
  })
  it('keeps leading-zero identifiers as text and distinguishes zero from blank', () => {
    expect(parseInput('00123', 'text')).toBe('00123')
    expect(parseInput('0', 'number')).toBe(0)
    expect(parseInput('', 'number')).toBeNull()
    expect(parseInput('1200.50', 'auto')).toBe(1200.5)
    expect(parseInput('00123', 'auto')).toBe('00123')
    expect(parseInput('12345678901234567', 'auto')).toBe('12345678901234567')
    expect(() => parseInput('1,200元', 'number')).toThrow('有效数字')
  })
  it('handles multi-letter columns and rejects reversed ranges', () => {
    expect(columnName(26)).toBe('AA')
    expect(rangeBounds('AA3:AB8')).toEqual([2, 26, 7, 27])
    expect(rangeBounds('B3:A1')).toBeNull()
    const task = example(), sheet = task.workbook.sheets[0]!
    expect(canFill(task, sheet, 2, 2)).toBe(true)
    expect(canFill(task, sheet, 1, 2)).toBe(false)
    expect(canFill({ ...task, status: 'closed' }, sheet, 2, 2)).toBe(false)
  })
})
