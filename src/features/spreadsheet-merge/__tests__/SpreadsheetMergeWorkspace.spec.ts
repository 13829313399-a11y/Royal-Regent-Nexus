import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { spreadsheetMergeApi, type MergeTemplate, type SpreadsheetInspection, type SpreadsheetMergePreview, type SpreadsheetMergeRequest } from '@/api/spreadsheetMerge'
import { advanceAuthenticationGeneration, announceSessionBoundary } from '@/lib/authenticationGeneration'
import { saveSpreadsheetBlob } from '../mergeHelpers'
import SpreadsheetMergeWorkspace from '../SpreadsheetMergeWorkspace.vue'

vi.mock('@/api/spreadsheetMerge', () => ({ spreadsheetMergeApi: { templates: vi.fn(), inspect: vi.fn(), preview: vi.fn(), export: vi.fn() } }))
vi.mock('../mergeHelpers', async importOriginal => ({ ...await importOriginal<object>(), saveSpreadsheetBlob: vi.fn() }))
const headers = ['货号', '产品名称', '备注']
const packagingTemplate: MergeTemplate = { id: 'carton-packaging', label: '货号包装导入模板', headers, profile: 'carton-packaging', description: '整理货号与纸品包装配置。', sheet_name: '导入数据', header_row: 1 }
const source: SpreadsheetInspection = { filename: '客户.xlsx', sheets: [{ name: '明细', rows: [headers, ['001', '', '原备注']] }, { name: '第二页', rows: [headers, ['002', '产品二', '']] }], warnings: [] }
function result(request?: SpreadsheetMergeRequest): SpreadsheetMergePreview {
  const resolution = request?.resolutions['p0:s0:c1'] ?? null
  return { headers, rows: [['001', '产品', '原备注']], provenance: [[{ table: 'secondary', name: '客户.xlsx / 明细', row: 2 }]], conflicts: [], issues: [], warnings: [], ready_for_import: true, stats: { primary_rows: 0, secondary_rows: 1, output_rows: 1, added_rows: 1, filled_cells: 0 }, validation_errors: [], ...(request?.key_columns.length ? { conflicts: [{ id: 'p0:s0:c1', row: 0, column: 1, primary: '原产品', secondary: '新产品', resolution }], ready_for_import: !!resolution } : {}) }
}
let wrapper: VueWrapper
function render() { wrapper = mount(SpreadsheetMergeWorkspace, { props: { factoryId: 'huaxing' } }); return wrapper }
async function pick(label: string, file = new File(['data'], '客户.xlsx')) {
  const input = wrapper.get(`input[aria-label="上传${label}"]`)
  Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
  await input.trigger('change')
  await flushPromises()
}
async function prepare() {
  render(); await flushPromises()
  await wrapper.get('[aria-label="主表来源"]').setValue('template')
  await pick('副表')
}
const button = (text: string) => wrapper.findAll('button').find(item => item.text() === text)!
beforeEach(() => {
  setActivePinia(createPinia())
  useAuthStore().isAuthenticated = true
  vi.mocked(spreadsheetMergeApi.templates).mockResolvedValue([packagingTemplate])
  vi.mocked(spreadsheetMergeApi.inspect).mockResolvedValue(source)
  vi.mocked(spreadsheetMergeApi.preview).mockImplementation(async request => result(request))
  vi.mocked(spreadsheetMergeApi.export).mockResolvedValue({ filename: '待补版.xlsx', blob: new Blob(['test']) })
})
afterEach(() => { wrapper?.unmount(); vi.clearAllMocks() })

describe('spreadsheet merge workspace', () => {
  it('preserves the chosen template and preview when only the session server clock changes', async () => {
    const auth = useAuthStore()
    auth.currentUser = {
      id: 'qa-user', username: 'qa-user', display_name: '测试用户', roles: [], permissions: [],
      factory_scopes: ['huaxing'], department_scopes: ['warehouse'], grants: [], force_password_change: false,
      identity: {
        identity_mode: 'v2', identity_version: 3, employment_epoch: 1, employment_status: 'active',
        primary_assignment: null, active_assignments_summary: [], assignments: [], primary_factory_id: 'huaxing',
        primary_department: 'warehouse', position: '仓库', server_now: '2026-10-19T10:00:00Z',
        next_transition_at: null, effective_context_key: 'warehouse-context',
      },
    }
    await prepare()
    await button('预览合并结果').trigger('click'); await flushPromises()
    const templateCalls = vi.mocked(spreadsheetMergeApi.templates).mock.calls.length
    auth.currentUser = { ...auth.currentUser, identity: { ...auth.currentUser.identity!, server_now: '2026-10-19T10:01:00Z' } }
    auth.sessionVersion++
    await flushPromises()
    expect(spreadsheetMergeApi.templates).toHaveBeenCalledTimes(templateCalls)
    expect((wrapper.get('[aria-label="主表来源"]').element as HTMLSelectElement).value).toBe('template')
    expect((wrapper.get('[aria-label="选择系统模板"]').element as HTMLSelectElement).value).toBe('carton-packaging')
    expect(wrapper.text()).toContain('核对合并结果')
  })
  it.each(['employment_epoch', 'identity_version', 'effective_context_key'] as const)('invalidates the template and preview when stable identity field %s changes', async field => {
    const auth = useAuthStore()
    auth.currentUser = {
      id: 'qa-user', username: 'qa-user', display_name: '测试用户', roles: [], permissions: [],
      factory_scopes: ['huaxing'], department_scopes: ['warehouse'], grants: [], force_password_change: false,
      identity: {
        identity_mode: 'v2', identity_version: 3, employment_epoch: 1, employment_status: 'active',
        primary_assignment: null, active_assignments_summary: [], assignments: [], primary_factory_id: 'huaxing',
        primary_department: 'warehouse', position: '仓库', server_now: '2026-10-19T10:00:00Z',
        next_transition_at: null, effective_context_key: 'warehouse-context',
      },
    }
    await prepare()
    await button('预览合并结果').trigger('click'); await flushPromises()
    const templateCalls = vi.mocked(spreadsheetMergeApi.templates).mock.calls.length
    if (field === 'effective_context_key') auth.currentUser.identity![field] = 'changed-context'
    else auth.currentUser.identity![field]++
    await flushPromises()
    expect(spreadsheetMergeApi.templates).toHaveBeenCalledTimes(templateCalls + 1)
    expect((wrapper.get('[aria-label="主表来源"]').element as HTMLSelectElement).value).toBe('upload')
    expect(wrapper.text()).not.toContain('核对合并结果')
  })
  it('shows all authorized carton templates and uses each returned header layout and description', async () => {
    const catalog: MergeTemplate[] = [
      packagingTemplate,
      { ...packagingTemplate, id: 'carton-paper-options', label: '纸品选项模板', profile: 'generic', description: '填写纸品类型与纸质。' },
      { ...packagingTemplate, id: 'carton-locations', label: '仓位模板', profile: 'generic', description: '填写仓库与仓位范围。' },
      { ...packagingTemplate, id: 'carton-history-orders', label: '历史订单模板', profile: 'generic', description: '填写已发生的历史订单。', header_row: 2 },
      { ...packagingTemplate, id: 'carton-opening-inventory', label: '期初库存模板', profile: 'generic', description: '填写切换期初的实物库存。', header_row: 2 },
      { ...packagingTemplate, id: 'carton-weekly-schedule', label: '周排期模板', profile: 'generic', description: '填写每周到货需求。', header_row: 3 },
    ]
    vi.mocked(spreadsheetMergeApi.templates).mockResolvedValue(catalog)
    await prepare()
    expect(wrapper.findAll('[aria-label="选择系统模板"] option')).toHaveLength(6)
    for (const template of catalog) {
      await wrapper.get('[aria-label="选择系统模板"]').setValue(template.id)
      expect(wrapper.text()).toContain(template.description)
      await button('预览合并结果').trigger('click'); await flushPromises()
      expect(vi.mocked(spreadsheetMergeApi.preview).mock.calls.at(-1)?.[0]).toMatchObject({ template_id: template.id, factory_id: 'huaxing', profile: template.profile, primary: { header_row: template.header_row } })
    }
  })
  it('hides an unavailable system catalog while preserving ordinary file merging', async () => {
    vi.mocked(spreadsheetMergeApi.templates).mockResolvedValue([])
    render(); await flushPromises()
    expect(wrapper.find('[aria-label="主表来源"] option[value="template"]').exists()).toBe(false)
    await pick('主表'); await pick('副表')
    await button('预览合并结果').trigger('click'); await flushPromises()
    const request = vi.mocked(spreadsheetMergeApi.preview).mock.calls.at(-1)?.[0]
    expect(request?.profile).toBe('generic')
    expect(request).not.toHaveProperty('template_id')
    expect(request).not.toHaveProperty('factory_id')
  })
  it('distinguishes loading and failed catalogs from an empty authorized list and offers retry', async () => {
    let rejectCatalog!: (reason: Error) => void
    vi.mocked(spreadsheetMergeApi.templates).mockImplementationOnce(() => new Promise((_, reject) => { rejectCatalog = reject }))
    render()
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('正在读取当前厂区的可用系统模板')
    expect(wrapper.text()).not.toContain('没有可用系统模板')
    rejectCatalog(new Error('连接超时')); await flushPromises()
    expect(wrapper.text()).toContain('系统模板读取失败：连接超时')
    expect(wrapper.text()).not.toContain('没有可用系统模板')
    await button('重新读取模板').trigger('click'); await flushPromises()
    expect(wrapper.find('[aria-label="主表来源"] option[value="template"]').exists()).toBe(true)
  })
  it('clears old templates and previews when factory or authorization changes and ignores late catalogs', async () => {
    await prepare()
    await button('预览合并结果').trigger('click'); await flushPromises()
    let oldCatalog!: (value: MergeTemplate[]) => void
    vi.mocked(spreadsheetMergeApi.templates).mockImplementationOnce(() => new Promise(resolve => { oldCatalog = resolve }))
    useAuthStore().authorizationVersion++
    await flushPromises()
    expect(wrapper.text()).not.toContain('核对合并结果')
    expect(wrapper.find('[aria-label="主表来源"] option[value="template"]').exists()).toBe(false)
    vi.mocked(spreadsheetMergeApi.templates).mockResolvedValue([])
    await wrapper.setProps({ factoryId: 'huakang-c' }); await flushPromises()
    oldCatalog([packagingTemplate]); await flushPromises()
    expect(spreadsheetMergeApi.templates).toHaveBeenLastCalledWith('huakang-c', expect.any(AbortSignal))
    expect(wrapper.find('[aria-label="主表来源"] option[value="template"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="副表工作表"]').exists()).toBe(false)
  })
  it('reloads the visible catalog on an account boundary and rejects an old catalog response', async () => {
    let staleCatalog!: (value: MergeTemplate[]) => void
    vi.mocked(spreadsheetMergeApi.templates).mockImplementationOnce(() => new Promise(resolve => { staleCatalog = resolve }))
    render()
    vi.mocked(spreadsheetMergeApi.templates).mockResolvedValue([])
    advanceAuthenticationGeneration(); announceSessionBoundary(); await flushPromises()
    staleCatalog([packagingTemplate]); await flushPromises()
    expect(spreadsheetMergeApi.templates).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[aria-label="主表来源"] option[value="template"]').exists()).toBe(false)
  })
  it('uses the system template and explicit source header selection', async () => {
    await prepare()
    await button('预览合并结果').trigger('click'); await flushPromises()
    expect(spreadsheetMergeApi.templates).toHaveBeenCalledWith('huaxing', expect.any(AbortSignal))
    expect(spreadsheetMergeApi.preview).toHaveBeenCalledWith(expect.objectContaining({ primary: { name: '货号包装导入模板', headers, rows: [], header_row: 1 }, secondary: expect.objectContaining({ rows: [['001', '', '原备注']], header_row: 1 }), profile: 'carton-packaging', template_id: 'carton-packaging', factory_id: 'huaxing', key_columns: [] }), expect.any(AbortSignal))
    expect(wrapper.text()).toContain('输出行')
    await wrapper.get('[aria-label="副表工作表"]').setValue('第二页')
    expect(wrapper.text()).not.toContain('核对合并结果')
    await button('预览合并结果').trigger('click'); await flushPromises()
    expect(vi.mocked(spreadsheetMergeApi.preview).mock.calls.at(-1)?.[0].secondary.rows[0]?.[0]).toBe('002')
  })
  it('requires conflict decisions and clears both preview and decisions when rules change', async () => {
    await prepare()
    await wrapper.get('[aria-label="匹配字段 货号"]').setValue(true)
    await button('预览合并结果').trigger('click'); await flushPromises()
    expect(button('下载待补版').attributes('disabled')).toBeDefined()
    await button('采用副表').trigger('click'); await flushPromises()
    expect(vi.mocked(spreadsheetMergeApi.preview).mock.calls.at(-1)?.[0].resolutions).toEqual({ 'p0:s0:c1': 'secondary' })
    expect(button('下载合并结果').attributes('disabled')).toBeUndefined()
    await wrapper.get('[aria-label="备注输出列"]').setValue(-1)
    expect(wrapper.text()).not.toContain('核对合并结果')
    await button('预览合并结果').trigger('click'); await flushPromises()
    expect(vi.mocked(spreadsheetMergeApi.preview).mock.calls.at(-1)?.[0].resolutions).toEqual({})
  })
  it('exports incomplete results explicitly as pending without filling product names', async () => {
    await prepare()
    vi.mocked(spreadsheetMergeApi.preview).mockResolvedValue({ ...result(), ready_for_import: false, validation_errors: ['产品名称必填'] })
    await button('预览合并结果').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('产品名称必填')
    await button('下载待补版').trigger('click'); await flushPromises()
    expect(spreadsheetMergeApi.export).toHaveBeenCalledWith(expect.objectContaining({ secondary: expect.objectContaining({ rows: [['001', '', '原备注']] }) }), expect.any(AbortSignal))
    expect(saveSpreadsheetBlob).toHaveBeenCalled()
  })
  it('sends the explicit paper-size preset and resets the source when format changes', async () => {
    vi.mocked(spreadsheetMergeApi.inspect).mockResolvedValue({ ...source, sheets: [...source.sheets, { name: '原表文字索引', rows: [['位置', '内容'], ['B8', '原文待核']] }] })
    render(); await flushPromises()
    await wrapper.get('[aria-label="主表来源"]').setValue('template')
    const select = wrapper.findAll('select').find(item => item.find('option[value="carton-packaging-source"]').exists())!
    await select.setValue('carton-packaging-source'); await pick('副表')
    expect(spreadsheetMergeApi.inspect).toHaveBeenCalledWith(expect.any(File), 'carton-packaging-source', expect.any(AbortSignal))
    await button('预览合并结果').trigger('click'); await flushPromises()
    expect(vi.mocked(spreadsheetMergeApi.preview).mock.calls.at(-1)?.[0].audit_tables).toEqual([{ name: '客户.xlsx / 原表文字索引', headers: ['位置', '内容'], rows: [['B8', '原文待核']], header_row: 1 }])
    await select.setValue('')
    expect(wrapper.findAll('input[type=number]').length).toBe(0)
  })
  it('sends composite matching keys and only explicitly selected extra fields to remarks', async () => {
    vi.mocked(spreadsheetMergeApi.inspect).mockResolvedValue({ ...source, sheets: [{ name: '明细', rows: [[...headers, '客户'], ['001', '', '原备注', '客户甲']] }] })
    await prepare()
    await wrapper.get('[aria-label="匹配字段 货号"]').setValue(true)
    await wrapper.get('[aria-label="匹配字段 产品名称"]').setValue(true)
    const extra = wrapper.findAll('label').find(item => item.text() === '客户')!.get('input')
    await extra.setValue(true)
    await button('预览合并结果').trigger('click'); await flushPromises()
    expect(vi.mocked(spreadsheetMergeApi.preview).mock.calls.at(-1)?.[0]).toMatchObject({ key_columns: [0, 1], remarks_column: 2, extra_columns_to_remarks: [3] })
    await wrapper.get('[aria-label="备注输出列"]').setValue(-1)
    await button('预览合并结果').trigger('click'); await flushPromises()
    expect(vi.mocked(spreadsheetMergeApi.preview).mock.calls.at(-1)?.[0].extra_columns_to_remarks).toEqual([])
  })
  it('does not hand off a stale download after rules change', async () => {
    await prepare()
    await button('预览合并结果').trigger('click'); await flushPromises()
    let resolveExport!: (value: { filename: string; blob: Blob }) => void
    vi.mocked(spreadsheetMergeApi.export).mockImplementation(() => new Promise(resolve => { resolveExport = resolve }))
    await button('下载合并结果').trigger('click')
    await wrapper.get('[aria-label="备注输出列"]').setValue(-1)
    resolveExport({ filename: '旧文件.xlsx', blob: new Blob(['old']) }); await flushPromises()
    expect(saveSpreadsheetBlob).not.toHaveBeenCalled()
  })
  it('ignores stale previews after input changes and source reads after session boundaries', async () => {
    await prepare()
    let resolvePreview!: (value: SpreadsheetMergePreview) => void
    vi.mocked(spreadsheetMergeApi.preview).mockImplementation(() => new Promise(resolve => { resolvePreview = resolve }))
    await button('预览合并结果').trigger('click')
    await wrapper.get('[aria-label="副表表头行"]').setValue(2)
    resolvePreview(result()); await flushPromises()
    expect(wrapper.text()).not.toContain('核对合并结果')
    let resolveSource!: (value: SpreadsheetInspection) => void
    vi.mocked(spreadsheetMergeApi.inspect).mockImplementation(() => new Promise(resolve => { resolveSource = resolve }))
    await pick('副表')
    advanceAuthenticationGeneration(); announceSessionBoundary()
    resolveSource(source); await flushPromises()
    expect(wrapper.find('[aria-label="副表工作表"]').exists()).toBe(false)
  })
})
