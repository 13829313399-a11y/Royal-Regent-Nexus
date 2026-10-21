import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Component from '../CartonSpecialManualReceipt.vue'
import type { SpecialRequest } from '@/api/cartonSpecialRequests'
const api = vi.hoisted(() => ({ manualReceive: vi.fn() }))
vi.mock('@/api/cartonSpecialRequests', () => ({ cartonSpecialRequestsApi: api }))
const picker = defineComponent({ props: ['effective'], emits: ['update:modelValue'], template: `<button type="button" aria-label="测试仓位" @click="$emit('update:modelValue', [{ location_id: 'BIN', quantity: effective }])">选择仓位</button>` })
const request = () => ({ id: 'R', request_no: 'SP1', factory_id: 'huaxing', revision: 3, status: 'SENT', permissions: { can_manual_receive: true }, shipments: [],
  lines: [{ id: 'L', packaging_type: '外箱', paper_quality: 'A=B', specification: '1*2*3', dimension_unit: 'cm', unit: '个', quantity: '99999999999999.9999', remaining_quantity: '99999999999999.9999', mark_mode: 'NONE' }] }) as unknown as SpecialRequest
const setup = (row = request()) => mount(Component, { props: { request: row, viewerKey: 'U', locations: [{ id: 'BIN', factory_id: 'huaxing', label: 'A01', warehouse: '仓库', bin_code: 'A01', status: 'ACTIVE' }] }, global: { stubs: { CartonReceiptAllocations: picker } } })
async function fill(w: ReturnType<typeof setup>, quantity = '10') { await w.get('[aria-label="手动收料送货单号"]').setValue('REAL-DN'); await w.get('[aria-label="L手动实收"]').setValue(quantity); await w.get('[aria-label="测试仓位"]').trigger('click') }
async function submit(w: ReturnType<typeof setup>) { await w.get('form').trigger('submit'); await flushPromises() }
beforeEach(() => { vi.clearAllMocks(); api.manualReceive.mockResolvedValue(request()) })
describe('sample and miscellaneous actual manual receipts', () => {
  it('keeps unknown or zero warehouse prices separate from supplier evidence and retries with the same identity', async () => {
    const w = setup(); await fill(w)
    expect(w.get('button[type="submit"]').text()).toBe('确认入库')
    api.manualReceive.mockRejectedValueOnce(new Error('未确认结果'))
    await submit(w)
    expect(w.get<HTMLInputElement>('[aria-label="手动收料送货单号"]').element.value).toBe('REAL-DN')
    const first = api.manualReceive.mock.calls[0]![1]
    expect(first).toMatchObject({ expected_revision: 3, delivery_note_no: 'REAL-DN', lines: [expect.objectContaining({ line_id: 'L', unit_price: null, location_allocations: [{ location_id: 'BIN', quantity: '10.0000' }] })] })
    expect(first.lines[0]).not.toHaveProperty('free_confirmed'); expect(first.lines[0]).not.toHaveProperty('supplier_unit_price')
    await submit(w); expect(api.manualReceive.mock.calls[1]![1].request_id).toBe(first.request_id)
    await w.get('[aria-label="L仓库记录单价"]').setValue('0'); await submit(w)
    expect(api.manualReceive.mock.calls[2]![1].lines[0].unit_price).toBe('0')
    expect(api.manualReceive.mock.calls[2]![1].lines[0]).not.toHaveProperty('zero_price_kind')
    w.unmount()
  })
  it('allows unconfirmed marks while retaining quantity and location checks', async () => {
    const row = request(); row.lines[0]!.mark_mode = 'PENDING'
    const w = setup(row); await fill(w)
    expect(w.text()).not.toContain('箱唛待确认，本次暂不可收料')
    await submit(w); expect(api.manualReceive).toHaveBeenCalledTimes(1)
    api.manualReceive.mockClear()
    await w.get('[aria-label="L手动破损"]').setValue('11'); await submit(w); expect(api.manualReceive).not.toHaveBeenCalled()
    await w.get('[aria-label="L手动破损"]').setValue('1'); await w.setProps({ locations: [] }); await submit(w); expect(api.manualReceive).not.toHaveBeenCalled(); expect(w.text()).toContain('须选择本厂仓位')
    w.unmount()
  })
  it('keeps large and fractional allocations exact without floating point subtraction', async () => {
    const w = setup(); await fill(w, '99999999999999.9999')
    await w.get('[aria-label="L手动破损"]').setValue('0.0001'); await w.get('[aria-label="L手动拒收"]').setValue('0.0002'); await w.get('[aria-label="L手动不可用"]').setValue('0.0003')
    await submit(w)
    expect(api.manualReceive.mock.calls[0]![1].lines[0].location_allocations[0].quantity).toBe('99999999999999.9993')
    w.unmount()
  })
  it('blocks a stale manual entry when an existing delivery wins the race and navigates without the attempted new note number', async () => {
    const w = setup(); await fill(w)
    api.manualReceive.mockRejectedValueOnce({ response: { data: { detail: { code: 'EXISTING_DELIVERY_PENDING', message: '存在其他待收单', delivery_ids: ['OLD'] } } } })
    await submit(w); await submit(w)
    expect(api.manualReceive).toHaveBeenCalledTimes(1)
    await w.findAll('button').find(button => button.text() === '查看待收送货单')!.trigger('click')
    expect(w.emitted('open-delivery')).toEqual([['']])
    expect(w.get<HTMLInputElement>('[aria-label="手动收料送货单号"]').element.value).toBe('REAL-DN')
    w.unmount()
  })
  it('clears drafts across account changes and ignores late old-account completion', async () => {
    let resolve!: (row: SpecialRequest) => void
    api.manualReceive.mockReturnValue(new Promise<SpecialRequest>(done => { resolve = done }))
    const w = setup(); await fill(w); await w.get('form').trigger('submit')
    await w.setProps({ viewerKey: 'OTHER' }); resolve(request()); await flushPromises()
    expect(w.emitted('saved')).toBeUndefined()
    expect(w.get<HTMLInputElement>('[aria-label="手动收料送货单号"]').element.value).toBe('')
    w.unmount()
  })
  it('blocks submission after operation permission is revoked without deleting the current draft', async () => {
    const w = setup(); await fill(w)
    await w.setProps({ request: { ...request(), permissions: { can_manual_receive: false } } })
    await submit(w)
    expect(api.manualReceive).not.toHaveBeenCalled()
    expect(w.get<HTMLInputElement>('[aria-label="手动收料送货单号"]').element.value).toBe('REAL-DN')
    w.unmount()
  })
})
