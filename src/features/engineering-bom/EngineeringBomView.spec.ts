import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { reactive } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import View from './EngineeringBomView.vue'
import { engineeringApi as api, newNode, type Bom, type Material, type ImportPreview } from './api'
import { useAuthStore } from '@/stores/auth'

vi.mock('@/stores/auth', async () => {
  const { reactive } = await import('vue')
  const store = reactive({ sessionVersion: 1, authorizationVersion: 1 })
  return { useAuthStore: () => store }
})
let wrapper: VueWrapper
const fixture = (): Bom => ({ id: 'bom-1', version: 1, effective_version: null, status: 'DRAFT', materials: {},
  data: { item_no: '001', name: '测试成品', specification: '', source_reference: '', nodes: [{ ...newNode(), key: 'root', source_name: '测试根项', process: '手工' }] } })
const button = (label: string) => wrapper.findAll('button').find(b => b.text() === label)!
async function start(boms: Bom[] = [fixture()], materials: Material[] = []) {
  vi.spyOn(api, 'access').mockResolvedValue({ enabled: true, schema_ready: true, permissions: ['read', 'bom_write', 'bom_approve', 'material_write', 'material_approve', 'import'] })
  vi.spyOn(api, 'workspace').mockResolvedValue({ materials, boms })
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: View }] })
  await router.push('/modules/engineering/bom?factory=huakang-c'); await router.isReady()
  wrapper = mount(View, { global: { plugins: [router], stubs: {
    PageHeader: { template: '<header><slot name="actions" /></header>' },
    SectionPanel: { props: ['title', 'subtitle'], template: '<section><h2>{{ title }}</h2><p>{{ subtitle }}</p><slot /></section>' },
  } } })
  await flushPromises()
  return router
}
beforeEach(() => { vi.restoreAllMocks(); vi.spyOn(window, 'confirm').mockReturnValue(true) })
afterEach(() => { wrapper?.unmount() })

describe('engineering BOM editor', () => {
  it('distinguishes same-name parent occurrences by their actual editor row', async () => {
    const existing = fixture()
    existing.data.nodes.push(...['part-a', 'part-b'].map(key => ({ ...newNode(), key, parent: 'root', process: '车缝', source_name: '同名部件' })),
      { ...newNode(), key: 'fabric', parent: 'part-b', process: '裁床' })
    await start([existing]); await button('查看／维护').trigger('click')
    const options = wrapper.get('[aria-label="第4行上级"]').findAll('option')
    expect(options.find(o => o.attributes('value') === 'part-a')!.text()).toBe('第2行 · 车缝 · 同名部件')
    expect(options.find(o => o.attributes('value') === 'part-b')!.text()).toBe('第3行 · 车缝 · 同名部件')
  })

  it.each(['手工', '车缝'] as const)('starts a %s finished BOM and adds children under the chosen occurrence', async process => {
    await start([])
    await wrapper.get('[aria-label="新建成品结构"]').setValue(process)
    await button('新建 BOM').trigger('click')
    const rootChildren = wrapper.findAll('[aria-label$="行上级"]')
    expect(rootChildren).toHaveLength(process === '手工' ? 2 : 1)
    const parentRow = process === '手工' ? 2 : 1
    const filter = wrapper.findAll('label').find(l => l.text().startsWith('按工序查看'))!.get('select')
    await filter.setValue('车缝')
    await wrapper.get(`[aria-label="第${parentRow}行新增下级"]`).trigger('click')
    expect(filter.element).toHaveProperty('value', '')
    expect(wrapper.get(`[aria-label="第${parentRow + 1}行上级"]`).isVisible()).toBe(true)
    const save = vi.spyOn(api, 'post').mockResolvedValue(fixture())
    await wrapper.get('form').trigger('submit'); await flushPromises()
    const body = save.mock.calls[0]![1] as { data: Bom['data'] }
    const nodes = body.data.nodes
    expect(nodes[0]).toMatchObject({ parent: '', process, numerator: '1', denominator: '1' })
    expect(nodes.at(-1)!.parent).toBe(nodes[parentRow - 1]!.key)
    if (process === '手工') expect(nodes[1]).toMatchObject({ parent: nodes[0]!.key, process: '车缝' })
    else expect(nodes.some(n => n.process === '手工')).toBe(false)
    expect(new Set(nodes.map(n => n.key)).size).toBe(nodes.length)
  })

  it.each([false, true])('requires explicit correction of pinned customer exemptions, including copying (%s)', async copy => {
    const existing = fixture()
    const m: Material = { id: 'supply', version: 2, code: '03-001', name: '供料件', status: 'ACTIVE',
      data: { unit: '个', engineering: { group: '03', department: '供料车间', attribute: '客供', approval: 'APPROVED' } } }
    existing.materials['supply:2'] = m
    existing.data.nodes.push({ ...newNode(), key: 'supply-row', parent: 'root', material_id: m.id, material_version: 2,
      source_name: m.name, source_code: m.code, unit: m.data.unit, exempt_loss: true, process: '手工' })
    const newer: Material = { ...m, version: 3, data: { ...m.data, engineering: { ...m.data.engineering!, attribute: '外购' } } }
    await start([existing], [newer])
    const save = vi.spyOn(api, 'post').mockResolvedValue({ ...existing, version: 2 })
    await button(copy ? '复制新货号' : '查看／维护').trigger('click')
    const checkbox = wrapper.get('[aria-label="第2行不计损耗"]')
    expect(checkbox.attributes('disabled')).toBeDefined()
    expect(checkbox.element).toHaveProperty('checked', true)
    expect(save).not.toHaveBeenCalled()
    await wrapper.get('[aria-label="第2行改为计损耗"]').trigger('click')
    expect(checkbox.element).toHaveProperty('checked', false)
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(save.mock.calls[0]![1]).toMatchObject({ data: { nodes: [existing.data.nodes[0], { ...existing.data.nodes[1], exempt_loss: false }] } })
    expect(existing.data.nodes[1]!.exempt_loss).toBe(true)
  })

  it('clears an exemption when explicitly selecting a customer material', async () => {
    const existing = fixture(), m: Material = { id: 's', version: 1, code: '03-001', name: '供料', status: 'ACTIVE',
      data: { unit: '个', engineering: { group: '03', department: '其它车间', attribute: '客供', approval: 'APPROVED' } } }
    existing.data.nodes.push({ ...newNode(), parent: 'root', exempt_loss: true })
    await start([existing], [m]); await button('查看／维护').trigger('click')
    await wrapper.get('[aria-label="第2行物料"]').setValue('s:1')
    expect(wrapper.get('[aria-label="第2行不计损耗"]').element).toHaveProperty('checked', false)
    expect(wrapper.get('[aria-label="第2行不计损耗"]').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('客供物料已设为计损耗')
  })

  it('fills only selected unmatched rows locally and preserves evidence until explicit save', async () => {
    const existing = fixture(), m: Material = { id: 'm1', code: '01-01-00001', name: '测试布', version: 2, status: 'ACTIVE',
      data: { unit: '码', engineering: { group: '01-01', attribute: '外购', department: '裁床', approval: 'APPROVED' } } }
    Object.assign(existing.data.nodes[0]!, { source_code: m.code, source_name: m.name, unit: '码', review_required: true, review_note: '核对原表', source: { '物料属性': '外购', row: '3' } })
    await start([existing], [m]); const save = vi.spyOn(api, 'post').mockResolvedValue({ ...existing, version: 2 })
    await button('查看／维护').trigger('click'); await button('查看未匹配用料候选').trigger('click')
    await wrapper.get('[aria-label="选择匹配第1行"]').setValue(true)
    await button('将勾选物料填入当前编辑内容').trigger('click')
    expect(save).not.toHaveBeenCalled(); expect(existing.data.nodes[0]!.material_id).toBe('')
    expect(button('审核当前草稿').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('已填入 1 条物料')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    const payload = save.mock.calls[0]![1] as { data: Bom['data'] }
    expect(payload.data.nodes[0]).toEqual({ ...existing.data.nodes[0], material_id: 'm1', material_version: 2 })
  })
  it('keeps matching unavailable when BOM write permission is absent', async () => {
    await start(); vi.mocked(api.access).mockResolvedValue({ enabled: true, schema_ready: true, permissions: ['read'] })
    await button('刷新资料').trigger('click'); await flushPromises(); await button('查看／维护').trigger('click')
    expect(button('查看未匹配用料候选').attributes('disabled')).toBeDefined()
  })
  it('opens material references, clears on refresh and reopens against the refreshed material version', async () => {
    const m: Material = { id: 'm1', code: '01-01-00001', name: '测试布', version: 2, status: 'ACTIVE',
      data: { unit: '码', engineering: { group: '01-01', attribute: '外购', department: '裁床', approval: 'APPROVED' } } }
    vi.spyOn(api, 'materialUsage').mockResolvedValue({ material_id: m.id, material_version: 2, code: m.code, name: m.name, checked_at: 'USAGE_TIME', bom_count: 0, items: [] })
    await start([], [m]); await button('物料档案').trigger('click'); await button('BOM 引用').trigger('click'); await flushPromises()
    expect(api.materialUsage).toHaveBeenLastCalledWith('m1', 2)
    expect(wrapper.text()).toContain('USAGE_TIME')
    vi.mocked(api.workspace).mockResolvedValue({ materials: [{ ...m, version: 3 }], boms: [] })
    await button('刷新资料').trigger('click'); await flushPromises()
    expect(wrapper.text()).not.toContain('USAGE_TIME')
    await button('BOM 引用').trigger('click'); await flushPromises()
    expect(api.materialUsage).toHaveBeenLastCalledWith('m1', 3)
    await button('维护').trigger('click')
    expect(wrapper.text()).not.toContain('USAGE_TIME')
    await wrapper.findAll('form input')[2]!.setValue('修改物料名称')
    expect(button('BOM 引用').attributes('disabled')).toBeDefined()
  })
  it('discards pending material references after revocation', async () => {
    const m: Material = { id: 'm1', code: '01-01-00001', name: '测试布', version: 2, status: 'ACTIVE',
      data: { unit: '码', engineering: { group: '01-01', attribute: '外购', department: '裁床', approval: 'APPROVED' } } }
    let finish!: (value: Awaited<ReturnType<typeof api.materialUsage>>) => void
    vi.spyOn(api, 'materialUsage').mockImplementation(() => new Promise(resolve => { finish = resolve }))
    await start([], [m]); await button('物料档案').trigger('click'); await button('BOM 引用').trigger('click')
    vi.mocked(api.access).mockRejectedValue({ response: { status: 403, data: { detail: '权限已撤销' } } })
    useAuthStore().authorizationVersion++; await flushPromises()
    finish({ material_id: m.id, material_version: 2, code: m.code, name: m.name, checked_at: 'SECRET_USAGE', bom_count: 0, items: [] })
    await flushPromises()
    expect(wrapper.text()).not.toContain('SECRET_USAGE'); expect(wrapper.text()).not.toContain('物料的 BOM 引用')
  })
  it('refreshes the open saved BOM after a version conflict so rechecking uses the current version', async () => {
    const existing = fixture(); await start([existing])
    const current = { ...existing, version: 2, data: { ...existing.data, name: '最新工程资料' } }
    vi.spyOn(api, 'approvalCheck').mockRejectedValueOnce({ response: { status: 409, data: { detail: 'BOM 已变化，请刷新资料后重新检查' } } })
      .mockResolvedValueOnce({ id: existing.id, version: 2, status: 'DRAFT', effective_version: null,
        checked_at: 'CURRENT_CHECK', checked_rows: 1, ready_for_approval: true, can_release: false, issues: [] })
    await button('查看／维护').trigger('click'); await button('检查已保存 BOM').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('BOM 已变化')
    vi.mocked(api.workspace).mockResolvedValue({ materials: [], boms: [current] })
    await button('刷新资料').trigger('click'); await flushPromises()
    await button('检查已保存 BOM').trigger('click'); await flushPromises()
    expect(api.approvalCheck).toHaveBeenLastCalledWith(existing.id, 2)
    expect(wrapper.text()).toContain('CURRENT_CHECK')
    expect(wrapper.findAll('input').some(input => input.element.value === '最新工程资料')).toBe(true)
  })
  it('clears approval checks on refresh and disables them for unsaved changes', async () => {
    await start()
    vi.spyOn(api, 'approvalCheck').mockResolvedValue({ id: 'bom-1', version: 1, status: 'DRAFT', effective_version: null,
      checked_at: 'CHECK_TIME', checked_rows: 1, ready_for_approval: true, can_release: false, issues: [] })
    expect(wrapper.text()).not.toContain('BOM 审核前检查')
    await button('查看／维护').trigger('click')
    await button('检查已保存 BOM').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('CHECK_TIME')
    await button('刷新资料').trigger('click'); await flushPromises()
    expect(wrapper.text()).not.toContain('CHECK_TIME')
    await button('检查已保存 BOM').trigger('click'); await flushPromises()
    await wrapper.get('[aria-label="第1行分子"]').setValue('1')
    expect(wrapper.text()).not.toContain('CHECK_TIME')
    expect(button('检查已保存 BOM').attributes('disabled')).toBeDefined()
    await button('新建 BOM').trigger('click')
    expect(wrapper.text()).not.toContain('BOM 审核前检查')
  })
  it('discards a pending approval check when engineering access is revoked', async () => {
    await start(); let finish!: (value: Awaited<ReturnType<typeof api.approvalCheck>>) => void
    vi.spyOn(api, 'approvalCheck').mockImplementation(() => new Promise(resolve => { finish = resolve }))
    await button('查看／维护').trigger('click'); await button('检查已保存 BOM').trigger('click')
    vi.mocked(api.access).mockRejectedValue({ response: { status: 403, data: { detail: '权限已撤销' } } })
    useAuthStore().authorizationVersion++; await flushPromises()
    finish({ id: 'bom-1', version: 1, status: 'DRAFT', effective_version: null, checked_at: 'SECRET_CHECK',
      checked_rows: 1, ready_for_approval: true, can_release: false, issues: [] })
    await flushPromises()
    expect(wrapper.text()).not.toContain('SECRET_CHECK'); expect(wrapper.text()).not.toContain('BOM 审核前检查')
  })
  it('opens comparison only for BOM history and discards a late result after revocation', async () => {
    const existing = fixture(), later = { ...existing, version: 2 }
    await start([later])
    vi.spyOn(api, 'history').mockResolvedValue({ items: [later, existing] })
    await button('历史').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('BOM 历史版本比较')
    let finish!: (value: Awaited<ReturnType<typeof api.compare>>) => void
    vi.spyOn(api, 'compare').mockImplementation(() => new Promise(resolve => { finish = resolve }))
    await button('比较已保存版本').trigger('click')
    vi.mocked(api.access).mockRejectedValue({ response: { status: 403, data: { detail: '无权限' } } })
    useAuthStore().authorizationVersion++; await flushPromises()
    finish({ id: existing.id, from_version: 1, to_version: 2, from_status: 'DRAFT', to_status: 'DRAFT', unchanged_count: 1,
      rows: [], header: [{ field: 'name', label: '名称', before: '', after: 'SECRET_BOM_DIFF' }] })
    await flushPromises()
    expect(wrapper.text()).not.toContain('SECRET_BOM_DIFF'); expect(wrapper.text()).not.toContain('BOM 历史版本比较')
  })
  it('shows a pinned historical material version and lets the engineer explicitly select the current version', async () => {
    const existing = fixture(), material: Material = { id: 'material-1', code: '01-01-00001', name: '新规格蓝布', version: 2,
      status: 'ACTIVE', data: { unit: '码', engineering: { group: '01-01', department: '裁床', attribute: '外购', approval: 'APPROVED' } } }
    Object.assign(existing.data.nodes[0]!, { material_id: material.id, material_version: 1, source_name: '旧规格蓝布', unit: '码' })
    await start([existing], [material]); await button('查看／维护').trigger('click')
    const select = wrapper.get<HTMLSelectElement>('[aria-label="第1行物料"]')
    expect(select.element.selectedOptions[0]!.text).toContain('历史 v1')
    await select.setValue('material-1:2')
    expect(wrapper.text()).toContain('物料 v2')
    expect(existing.data.nodes[0]!.material_version).toBe(1)
  })

  it('opens reactive records, saves a detached tree and retries an uncertain write with the same identity', async () => {
    const existing = fixture()
    await start([reactive(existing)])
    const save = vi.spyOn(api, 'post').mockRejectedValueOnce(new Error('连接中断')).mockResolvedValueOnce({ ...existing, version: 2 })
    await button('查看／维护').trigger('click')
    await wrapper.get('[aria-label="第1行分子"]').setValue('1')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(save).toHaveBeenCalledTimes(1)
    const payload = save.mock.calls[0]![1] as { operation_id: string; data: Bom['data'] }
    expect(payload.data.item_no).toBe('001')
    expect(payload.data).not.toBe(existing.data)
    expect(button('新建 BOM').attributes('disabled')).toBeDefined()
    await button('核对并重试原请求').trigger('click'); await flushPromises()
    expect(save.mock.calls[1]![1]).toEqual(payload)
    expect(wrapper.text()).toContain('已保存')
  })

  it('copies a different item without mutating the source and pins its source version', async () => {
    const existing = fixture(); await start([existing])
    const save = vi.spyOn(api, 'post').mockResolvedValue({ ...existing, id: 'new' })
    await button('复制新货号').trigger('click')
    const item = wrapper.findAll('label').find(l => l.text() === '货号')!.get('input')
    expect((item.element as HTMLInputElement).value).toBe('')
    await item.setValue('002'); await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(save.mock.calls[0]![0]).toBe('/boms')
    expect(save.mock.calls[0]![1]).toMatchObject({ copy_from: 'bom-1', copy_version: 1, data: { item_no: '002' } })
    expect(existing.data.item_no).toBe('001')
  })

  it('adopts an import with the source evidence and warnings intact', async () => {
    await start([])
    const result: ImportPreview = { filename: 'sample.xlsx', sha256: 'hash', row_count: 1, material_count: 1, can_save: true, issues: [], data: fixture().data }
    result.data.nodes[0]!.source = { row: '2', sheet: 'Sheet1', 标准用量: '1' }
    result.data.nodes[0]!.review_required = true
    vi.spyOn(api, 'importPreview').mockResolvedValue(result)
    await button('历史导入').trigger('click')
    const file = wrapper.get('input[type=file]')
    Object.defineProperty(file.element, 'files', { value: [new File(['test'], 'sample.xlsx')] })
    await file.trigger('change'); await flushPromises()
    await button('进入 BOM 草稿核对').trigger('click')
    expect(wrapper.text()).toContain('来源 Sheet1 第 2 行')
    expect(wrapper.text()).toContain('来源用量／物料待核对')
    expect(button('审核当前草稿').attributes('disabled')).toBeDefined()
  })

  it('discards late preview and history responses when the editor changes', async () => {
    await start()
    let finish!: (value: Awaited<ReturnType<typeof api.preview>>) => void
    let history!: (value: Awaited<ReturnType<typeof api.history>>) => void
    vi.spyOn(api, 'preview').mockImplementation(() => new Promise(resolve => { finish = resolve }))
    vi.spyOn(api, 'history').mockImplementation(() => new Promise(resolve => { history = resolve }))
    await button('查看／维护').trigger('click')
    await button('核对理论用量').trigger('click')
    await wrapper.get('[aria-label="第1行分子"]').setValue('2')
    finish({ items: [{ key: 'root', quantity: '999', unit: '码', process: '手工' }] }); await flushPromises()
    expect(wrapper.text()).not.toContain('999 码')
    await button('历史').trigger('click')
    await button('新建 BOM').trigger('click')
    history({ items: [fixture()] }); await flushPromises()
    expect(wrapper.text()).not.toContain('历史依据')
  })

  it('clears private content on permission changes and never restores a late old response', async () => {
    await start()
    let finish!: (value: Awaited<ReturnType<typeof api.history>>) => void
    vi.spyOn(api, 'history').mockImplementation(() => new Promise(resolve => { finish = resolve }))
    await button('历史').trigger('click')
    vi.mocked(api.access).mockRejectedValue({ response: { status: 403, data: { detail: '权限已撤销' } } })
    useAuthStore().authorizationVersion++
    await flushPromises(); finish({ items: [fixture()] }); await flushPromises()
    expect(wrapper.text()).toContain('权限已撤销')
    expect(wrapper.text()).not.toContain('测试成品')
    expect(wrapper.text()).not.toContain('历史依据')
  })
})
