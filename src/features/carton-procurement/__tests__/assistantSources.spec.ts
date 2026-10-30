import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { webcrypto } from 'node:crypto'
import CartonRecordSource from '../CartonRecordSource.vue'
import { cartonInventoryIdentity, cartonSelection } from '../assistantContext'
import type { UnifiedOrderEntry } from '@/api/cartonSpecialRequests'
import type { CartonOrderResponse } from '@/api/cartonProcurement'
import type { InventoryOrderReportRow } from '@/api/cartonInventoryReport'

const api = vi.hoisted(() => ({ selected: vi.fn(), inventory: vi.fn() }))
vi.mock('@/api/cartonSpecialRequests', () => ({ cartonSpecialRequestsApi: { selected: api.selected } }))
vi.mock('@/api/cartonInventoryReport', () => ({ cartonInventoryReportApi: { get: api.inventory } }))
const Dialog = defineComponent({ props: ['title'], emits: ['close'], template: '<section role="dialog"><h2>{{ title }}</h2><slot/><button @click="$emit(\'close\')">关闭</button></section>' })
const wrappers: VueWrapper[] = []
const props = { factoryId: 'huakang-a', resourceId: 'PURCHASE:P1', viewerKey: 'alice:1', scopeValid: true }
function purchase(factory = 'huakang-a'): UnifiedOrderEntry {
  return { kind: 'PURCHASE', order: { id: 'native-id', order_no: 'P1', factory_id: factory, customer_name: '合成客户',
    status: 'PARTIALLY_RECEIVED', due_date: '2026-10-24', updated_at: '2026-10-23T08:00:00+08:00', product_order_quantity: null,
    contract_no: 'CON', item_no: 'ITEM', lines: [{ id: 'line', packaging_type: '外箱', paper_quality: 'A33', specification: '1x1x1',
      unit: '个', required_quantity: '1000', received_quantity: '600', remaining_quantity: '400', usage_quantity: null }] } as CartonOrderResponse }
}
function open(extra = {}) {
  const wrapper = mount(CartonRecordSource, { props: { ...props, ...extra }, attachTo: document.body,
    global: { stubs: { CartonOrderDetailDialog: Dialog, CartonOrderTimeline: true } } })
  wrappers.push(wrapper)
  return wrapper
}
beforeEach(() => { vi.clearAllMocks(); vi.stubGlobal('crypto', webcrypto); api.selected.mockResolvedValue([purchase()]) })
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()); vi.unstubAllGlobals() })

it('reads the typed native selection, renders original unit quantities and records the trusted identifier', async () => {
  const wrapper = open(); await flushPromises()
  expect(api.selected).toHaveBeenCalledWith('huakang-a', [{ kind: 'PURCHASE', id: 'P1' }], expect.any(AbortSignal))
  expect(wrapper.text()).toContain('400 个')
  expect(wrapper.text()).toContain('1,000 个')
  expect(wrapper.text()).toContain('600 个')
  expect(wrapper.text()).toContain('未记录')
  expect(wrapper.text()).toContain('2026-10-23T08:00:00+08:00')
  expect(wrapper.emitted('selected')?.[0]).toEqual(['PURCHASE:P1', 'P1', { date_from: '', date_to: '' }])
  expect(wrapper.findAll('button').map(b => b.text())).toEqual(['关闭'])
})

it.each([true, false])('restores keyboard focus at the real dialog cleanup boundary (opener=%s)', async (hasOpener) => {
  const main = document.createElement('main')
  main.tabIndex = -1
  main.dataset.ylHelp = 'carton-procurement.overview'
  const opener = document.createElement('button')
  opener.textContent = '查看原记录'
  opener.setAttribute('data-carton-source-opener', '')
  main.append(opener)
  document.body.append(main)
  if (hasOpener) main.focus() // Router focus may move before the modal mounts.
  else (document.activeElement as HTMLElement | null)?.blur()
  const wrapper = mount(CartonRecordSource, { props: { ...props, returnFocus: hasOpener ? opener : null }, attachTo: main,
    global: { stubs: { CartonOrderTimeline: true } } })
  try {
    await flushPromises()
    await vi.waitFor(() => expect(document.activeElement?.closest('[role="dialog"]')).not.toBeNull())
    const restoredOpener = opener.cloneNode(true) as HTMLButtonElement
    if (hasOpener) opener.replaceWith(restoredOpener)
    wrapper.unmount()
    await vi.waitFor(() => expect(document.activeElement).toBe(hasOpener ? restoredOpener : main))
  } finally {
    if (wrapper.exists()) wrapper.unmount()
    main.remove()
  }
})

it('clears facts on failed refresh, supports retry, and never trusts another factory response', async () => {
  const wrapper = open(); await flushPromises()
  api.selected.mockResolvedValueOnce([purchase('huakang-b')])
  await wrapper.setProps({ viewerKey: 'alice:2' }); await flushPromises()
  expect(wrapper.get('[role="alert"]').text()).toContain('原订单已删除或不在当前可见范围')
  expect(wrapper.text()).not.toContain('600 个')
  await wrapper.findAll('button').find(b => b.text()==='重新读取')!.trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('600 个')
})

it('aborts the old read and rejects a late answer after identity changes', async () => {
  let complete!: (rows: UnifiedOrderEntry[]) => void
  api.selected.mockImplementationOnce(() => new Promise(resolve => { complete = resolve }))
  const wrapper = open(); await flushPromises()
  const signal = api.selected.mock.calls[0]![2] as AbortSignal
  api.selected.mockResolvedValueOnce([])
  await wrapper.setProps({ viewerKey: 'bob:2' }); await flushPromises()
  expect(signal.aborted).toBe(true)
  complete([purchase()]); await flushPromises()
  expect(wrapper.text()).not.toContain('600 个')
  expect(wrapper.emitted('selected')).toBeUndefined()
})

it('preserves the inventory period and distinguishes current positions from historical ending', async () => {
  const row = { key: '["huakang-a","C1",null,"CON","ITEM","外箱","A33","1x1x1","个"]',
    customer_name: '合成客户', contract_no: 'CON', item_no: 'ITEM', unit: '个', packaging_type: '外箱', paper_quality: 'A33', specification: '1x1x1',
    opening_quantity: '10', inbound_quantity: '5', outbound_quantity: '3', adjustment_quantity: '0', ending_quantity: '12',
    current_positions: [{ location: 'A01', quantity: '19' }], last_movement_at: '2026-10-21T08:00:00+08:00' } as InventoryOrderReportRow
  const id = await cartonInventoryIdentity(row.key)
  api.inventory.mockResolvedValue({ order_rows: [row], rows: [], movements: [] })
  const wrapper = open({ resourceId: id, dateFrom: '2026-10-20', dateTo: '2026-10-21' }); await flushPromises()
  await vi.waitFor(() => expect(wrapper.emitted('selected')).toHaveLength(1))
  expect(api.inventory).toHaveBeenCalledWith('huakang-a', { customer_code: '', search: '', date_from: '2026-10-20', date_to: '2026-10-21' }, expect.any(AbortSignal))
  expect(wrapper.text()).toContain('12 个')
  expect(wrapper.text()).toContain('A01：19 个')
  expect(wrapper.text()).toContain('源系统未提供，需另行核实')
  expect(wrapper.getComponent({ name: 'CartonOrderTimeline' }).props()).toMatchObject({ dateFrom: '2026-10-20', dateTo: '2026-10-21', orderId: '', inventoryKey: row.key })
})

it('rejects invalid scope, typed identities and dates before any native read', async () => {
  for (const extra of [{ scopeValid: false }, { resourceId: 'P1' }, { resourceId: 'PURCHASE: P1' },
    { dateFrom: '2026-02-30' }, { dateFrom: '2026-10-23' }]) {
    const wrapper = open(extra); await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    wrapper.unmount()
  }
  expect(api.selected).not.toHaveBeenCalled()
  expect(api.inventory).not.toHaveBeenCalled()
})

it('does not silently truncate an oversized selection into a different query scope', () => {
  const result = cartonSelection('huakang-a', Array.from({ length: 11 }, (_, i) => `PURCHASE:${i}`), {})
  expect(result.resources).toEqual([])
  expect(result.filters.scope_error).toContain('10条')
  const accepted = cartonSelection('huakang-a', Array.from({ length: 10 }, (_, i) => `PURCHASE:${'x'.repeat(80)}${i}`), {})
  expect(accepted.resources).toHaveLength(10)
  expect(accepted.selection_id.length).toBeLessThanOrEqual(96)
})
