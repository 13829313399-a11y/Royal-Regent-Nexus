import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import ImportDialog from '../CartonOrderImportDialog.vue'
import { pendingCartonBatches } from '@/features/carton-procurement/batchOrders'
import type { ImportFile, ImportPreview, ImportRow } from '@/api/cartonOrderImport'

const api = vi.hoisted(() => ({ read: vi.fn(), preview: vi.fn(), confirm: vi.fn(), importDemands: vi.fn() }))
vi.mock('@/api/cartonOrderImport', () => ({ cartonOrderImportApi: api }))
vi.mock('@/api/cartonBatchOrders', () => ({ cartonBatchOrdersApi: api }))
const stubs = Object.fromEntries(['DialogRoot', 'DialogPortal', 'DialogOverlay', 'DialogContent', 'DialogTitle', 'DialogDescription'].map(name => [name, { template: '<div><slot /></div>' }]))
const props = { open: true, factoryId: 'huaxing', viewerKey: 'actor-auth1', identityKey: 'actor', mode: 'SPECIAL' as const, file: new File(['source'], '需求.xlsx') }
const source: ImportRow[] = [{ source_row: 2, data: { group: 'A', kind: '', item_no: '001', packaging_type: '外箱', paper_quality: 'A33', specification: '20*10*8', dimension_unit: 'cm', quantity: '12', unit: '个', required_date: '', note: '' } }, { source_row: 3, data: { group: 'B', packaging_type: '内盒', unit: '' } }]
function file(): ImportFile { return { fingerprint: 'a'.repeat(64), sheets: ['自有表'], sheet: '自有表', header_row: 1, mapping: { group: 1, quantity: 2 }, rows: structuredClone(source), fields: [{ key: 'group', label: '分组编号' }, { key: 'quantity', label: '指定采购数量' }, { key: 'required_date', label: '需用日期' }], columns: [{ index: 1, label: '分组', sample: 'A' }, { index: 2, label: '数量', sample: '12' }] } }
function preview(): ImportPreview { return { preview_fingerprint: 'b'.repeat(64), groups: [{ id: 'G-2', label: 'A', source_rows: [2], status: 'READY', quantities: ['12'], errors: [], warnings: [], due_date: '2026-11-02' }, { id: 'G-3', label: 'B', source_rows: [3], status: 'INVALID', quantities: [], errors: ['缺少纸质和规格'], warnings: [], due_date: '' }] } }
const button = (wrapper: ReturnType<typeof mount>, label: string) => wrapper.findAll('button').find(b => b.text() === label)!
beforeEach(() => { vi.resetAllMocks(); pendingCartonBatches.clear(); api.read.mockImplementation(async () => file()); api.preview.mockImplementation(async () => preview()) })

it('matches arbitrary columns and submits whole ready groups while preserving incomplete rows', async () => {
  api.confirm.mockResolvedValue({ count: 1, batch_id: 'B1' })
  const wrapper = mount(ImportDialog, { props, global: { stubs } }); await flushPromises()
  await wrapper.get('[aria-label="匹配指定采购数量"]').setValue('2')
  await button(wrapper, '核对订单').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('可导入 1 单 · 待补充 1 单')
  expect(wrapper.get('[aria-label="选择订单 B"]').attributes('disabled')).toBeDefined()
  await wrapper.get('form').trigger('submit'); await flushPromises()
  const body = api.confirm.mock.calls[0]![0]
  expect(body.selected_groups).toEqual(['G-2'])
  expect(body.rows).toHaveLength(2)
  expect(body.mapping.quantity).toBe(2)
  expect(wrapper.emitted('saved')).toHaveLength(1)
  expect(wrapper.emitted('update:open')).toBeUndefined()
  expect(wrapper.text()).toContain('其余订单仍保留在本次预览')
  wrapper.unmount()
})

it('requires revalidation after corrections and retries the exact frozen body/file after a timeout', async () => {
  api.confirm.mockRejectedValueOnce(new Error('断网')).mockResolvedValueOnce({ count: 1, batch_id: 'B1' })
  const wrapper = mount(ImportDialog, { props, global: { stubs } }); await flushPromises()
  await button(wrapper, '核对订单').trigger('click'); await flushPromises()
  await wrapper.get('[aria-label="导入统一日期"]').setValue('2026-11-02')
  await button(wrapper, '填入空白项').trigger('click')
  expect(button(wrapper, '导入所选 0 张订单').attributes('disabled')).toBeDefined()
  await button(wrapper, '补充／修改资料').trigger('click')
  await wrapper.get('[aria-label="第 2 行指定采购数量"]').setValue('12.25')
  await button(wrapper, '重新校验').trigger('click'); await flushPromises()
  await wrapper.get('form').trigger('submit'); await flushPromises()
  const original = api.confirm.mock.calls[0]![0]
  expect(original.rows[0].data).toMatchObject({ kind: '样板单', required_date: '2026-11-02', quantity: '12.25' })
  await wrapper.setProps({ open: false }); await wrapper.setProps({ open: true, viewerKey: 'actor-auth2', file: null }); await flushPromises()
  expect(wrapper.text()).toContain('原提交结果待核对')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(api.confirm.mock.calls[1]![0]).toEqual(original)
  expect(api.confirm.mock.calls[1]![1]).toBe(props.file)
  expect(pendingCartonBatches.size).toBe(0)
  wrapper.unmount()
})

it('discards late file results and reauthorizes retained data on scope changes', async () => {
  let resolve!: (data: ImportFile) => void
  api.read.mockImplementationOnce(() => new Promise(r => { resolve = r })).mockRejectedValueOnce(new Error('无权限'))
  const wrapper = mount(ImportDialog, { props, global: { stubs } })
  await wrapper.setProps({ factoryId: 'huakang-a' }); await flushPromises()
  resolve(file()); await flushPromises()
  expect(wrapper.text()).toContain('无权限')
  expect(wrapper.find('[aria-label="匹配分组编号"]').exists()).toBe(false)
  expect(api.preview).not.toHaveBeenCalled()
  wrapper.unmount()
})

it('keeps upgrade-time legacy uncertain imports on their original endpoint and key', async () => {
  const legacy = { factory_id: props.factoryId, request_id: 'old-request-123456', fingerprint: 'a'.repeat(64), rows: source.slice(0, 1).map(r => ({ source_row: r.source_row, ...r.data })) }
  pendingCartonBatches.set('import:actor:huaxing', { body: legacy, file: props.file, uncertain: true })
  api.importDemands.mockResolvedValue({ count: 1, batch_id: 'OLD' })
  const wrapper = mount(ImportDialog, { props: { ...props, file: null }, global: { stubs } }); await flushPromises()
  expect(wrapper.text()).toContain('核对升级前的原提交')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(api.importDemands.mock.calls[0]![0]).toEqual(legacy)
  expect(api.confirm).not.toHaveBeenCalled()
  expect(pendingCartonBatches.size).toBe(0)
  wrapper.unmount()
})

it('shows authoritative field requirements and excludes the template example from preview and submission', async () => {
  api.read.mockResolvedValue({ ...file(), ignored_demo_rows: [2], rows: [{ source_row: 3, data: source[0]!.data }], fields: [
    { key: 'group', label: '分组编号', requirement: 'required', hint: '同一订单全部纸品填写相同分组编号。' },
    { key: 'note', label: '备注', requirement: 'optional', hint: '无备注可留空。' },
    { key: 'quantity', label: '指定采购数量', requirement: 'conditional', hint: '按装箱规则计算时可留空。' },
  ] })
  const wrapper = mount(ImportDialog, { props, global: { stubs } }); await flushPromises()
  expect(wrapper.text()).toContain('已跳过 1 行演示（原表第 2 行）')
  for (const text of ['分组编号 （必填）', '备注 （选填）', '指定采购数量 （按条件必填）', '按装箱规则计算时可留空。']) expect(wrapper.text()).toContain(text)
  api.preview.mockResolvedValue({ ...preview(), groups: [{ ...preview().groups[0], id: 'G-3', source_rows: [3] }] })
  await button(wrapper, '核对订单').trigger('click'); await flushPromises()
  expect(api.preview.mock.calls[0]![0].rows.map((r: ImportRow) => r.source_row)).toEqual([3])
  api.confirm.mockResolvedValue({ count: 1, batch_id: 'B1' })
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(api.confirm.mock.calls[0]![0].rows.map((r: ImportRow) => r.source_row)).toEqual([3])
  wrapper.unmount()
})

it('explains an example-only workbook without previewing or importing it', async () => {
  api.read.mockResolvedValue({ ...file(), ignored_demo_rows: [2], rows: [] })
  const wrapper = mount(ImportDialog, { props, global: { stubs } }); await flushPromises()
  expect(wrapper.text()).toContain('当前没有待导入的实际数据')
  await button(wrapper, '核对订单').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('已跳过演示行，没有待导入的实际数据')
  expect(api.preview).not.toHaveBeenCalled()
  expect(api.confirm).not.toHaveBeenCalled()
  wrapper.unmount()
})
