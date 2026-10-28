import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import AppendDialog from '../CartonBatchAppendDialog.vue'
import ImportDialog from '../CartonDemandImportDialog.vue'
import { appendDraft, appendItems, pendingCartonBatches, sumQuantity } from '@/features/carton-procurement/batchOrders'
import type { UnifiedOrderEntry } from '@/api/cartonSpecialRequests'

const api = vi.hoisted(() => ({ selected: vi.fn(), append: vi.fn(), preview: vi.fn(), import: vi.fn() }))
vi.mock('@/api/cartonSpecialRequests', () => ({ cartonSpecialRequestsApi: api }))
vi.mock('@/api/cartonBatchOrders', () => ({ cartonBatchOrdersApi: api }))
const stubs = Object.fromEntries(['DialogRoot', 'DialogPortal', 'DialogOverlay', 'DialogContent', 'DialogTitle', 'DialogDescription'].map(name => [name, { template: '<div><slot /></div>' }]))
const entry = { kind: 'SAMPLE', special: { id: 'R1', request_no: 'SP-01', revision: 3, required_date: '2026-11-01', lines: [{ id: 'L1', item_no: '001', packaging_type: '外箱', paper_quality: 'A33', specification: '20*10*8', dimension_unit: 'cm', quantity: '10.125', unit: '个' }] } } as UnifiedOrderEntry
const props = { open: true, factoryId: 'huaxing', viewerKey: 'actor-auth1', identityKey: 'actor', selection: [{ kind: 'SAMPLE' as const, id: 'R1', expected_revision: 3 }] }
beforeEach(() => { vi.resetAllMocks(); pendingCartonBatches.clear(); api.selected.mockResolvedValue([entry]) })

it('preserves exact increments, ignores zero and refuses reductions or overflow', () => {
  expect(sumQuantity('99999999999998.9999', '0.0001')).toBe('99999999999999')
  expect(sumQuantity('99999999999999.9999', '0.0001')).toBe('数量无效')
  expect(sumQuantity('10', '')).toBe('10')
  const draft = appendDraft(entry)
  expect(appendItems([draft], '')).toEqual([])
  draft.lines[0]!.addition = '0.1250'
  expect(appendItems([draft], '客户追加需求')[0]!.lines).toEqual([{ id: 'L1', additional_quantity: '0.1250' }])
  draft.lines[0]!.addition = '-1'
  expect(() => appendItems([draft], '客户追加需求')).toThrow()
})

it('restores the original frozen quantities and replays only the original command after timeout', async () => {
  api.append.mockRejectedValueOnce(new Error('断网')).mockResolvedValueOnce({ count: 1, batch_id: 'B1' })
  const unmodified = { ...entry, special: { ...entry.special!, id: 'R2', request_no: 'SP-02' } }
  api.selected.mockResolvedValueOnce([entry, unmodified])
  const wrapper = mount(AppendDialog, { props: { ...props, selection: [...props.selection, { kind: 'SAMPLE', id: 'R2', expected_revision: 3 }] }, global: { stubs } }); await flushPromises()
  await wrapper.get('[aria-label="批量追加原因"]').setValue('客户增加需求')
  await wrapper.get('[aria-label="SP-01 L1 本次追加数量"]').setValue('2.125')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  const original = api.append.mock.calls[0]![0]
  await wrapper.setProps({ open: false }); await flushPromises()
  api.selected.mockResolvedValue([{ ...entry, special: { ...entry.special, revision: 4, lines: [{ ...entry.special!.lines[0], quantity: '12.25' }] } }])
  await wrapper.setProps({ open: true, viewerKey: 'actor-auth2' }); await flushPromises()
  expect(api.selected.mock.calls.at(-1)![1]).toEqual([{ kind: 'SAMPLE', id: 'R1', expected_revision: 3 }])
  expect((wrapper.get('[aria-label="SP-01 L1 本次追加数量"]').element as HTMLInputElement).value).toBe('2.125')
  expect(wrapper.text()).toContain('10.125 个')
  expect(wrapper.text()).toContain('12.25 个')
  expect(wrapper.text()).not.toContain('SP-02')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(api.append.mock.calls[1]![0]).toEqual(original)
  expect(wrapper.emitted('saved')).toHaveLength(1)
  expect(pendingCartonBatches.size).toBe(0)
  wrapper.unmount()
})

it('fills only missing import fields and retains edited rows and file on unknown-result retry', async () => {
  const file = new File(['source'], '需求.xlsx')
  api.preview.mockResolvedValue({ fingerprint: 'a'.repeat(64), rows: [{ source_row: 2, group: 'A', kind: '', item_no: '001', packaging_type: '外箱', paper_quality: 'A33', specification: '20*10*8', dimension_unit: 'inch', quantity: '12', unit: '个', required_date: '', note: '' }] })
  api.import.mockRejectedValueOnce(new Error('断网')).mockResolvedValueOnce({ count: 1, batch_id: 'I1' })
  const wrapper = mount(ImportDialog, { props: { ...props, file }, global: { stubs } }); await flushPromises()
  await wrapper.get('[aria-label="导入统一需用日期"]').setValue('2026-11-02')
  await wrapper.findAll('button').find(b => b.text() === '填入所选空白项')!.trigger('click')
  await wrapper.get('[aria-label="第 2 行数量"]').setValue('12.25')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  const original = api.import.mock.calls[0]![0]
  expect(original.rows[0]).toMatchObject({ kind: '样板单', required_date: '2026-11-02', quantity: '12.25', dimension_unit: 'in' })
  expect(original.rows[0]).not.toHaveProperty('selected')
  await wrapper.setProps({ open: false }); await wrapper.setProps({ open: true, file: null }); await flushPromises()
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(api.import.mock.calls[1]![0]).toEqual(original)
  expect(api.import.mock.calls[1]![1]).toBe(file)
  expect(wrapper.emitted('saved')).toHaveLength(1)
  wrapper.unmount()
})

it('discards late selection results when factory changes', async () => {
  let resolve!: (value: UnifiedOrderEntry[]) => void
  api.selected.mockImplementationOnce(() => new Promise(r => { resolve = r })).mockResolvedValueOnce([])
  const wrapper = mount(AppendDialog, { props, global: { stubs } })
  await wrapper.setProps({ factoryId: 'huakang-a', selection: [] }); await flushPromises()
  resolve([entry]); await flushPromises()
  expect(wrapper.text()).not.toContain('SP-01')
  expect(api.append).not.toHaveBeenCalled()
  wrapper.unmount()
})
