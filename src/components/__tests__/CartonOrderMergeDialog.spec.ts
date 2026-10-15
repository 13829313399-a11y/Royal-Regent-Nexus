import { flushPromises, mount } from '@vue/test-utils'
import { reactive } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Component from '../CartonOrderMergeDialog.vue'
import { cartonProcurementApi, type CartonOrderResponse } from '@/api/cartonProcurement'
import { mergeOrderContract, mergeStorageKey } from '@/features/carton-procurement/contractMerge'

const mocks = vi.hoisted(() => ({ auth: {} as { currentUser?: { id: string; identity: { employment_epoch: number } }; authorizationVersion?: number; can?: typeof vi.fn }, can: vi.fn(() => true) }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => mocks.auth }))
vi.mock('@/api/cartonProcurement', () => ({ cartonProcurementApi: { listOrders: vi.fn() } }))
vi.mock('@/features/carton-procurement/contractMerge', async original => ({ ...await original<typeof import('@/features/carton-procurement/contractMerge')>(), mergeOrderContract: vi.fn() }))
vi.mock('@/lib/http', () => ({ http: {}, getApiErrorMessage: (error: Error) => error.message }))
function order(n: number, overrides = {}): CartonOrderResponse {
  return { id: `O${n}`, order_no: `ORD-${n}`, factory_id: 'huaxing', supplier_id: 'S', customer_code: 'C', customer_name: '客户', contract_no: `OLD-${n}`, customer_po: `PO-${n}`, item_no: `ITEM-${n}`, status: 'CONFIRMED', revision: n, lines: [], ...overrides } as CartonOrderResponse
}
beforeEach(() => {
  localStorage.clear(); vi.resetAllMocks(); mocks.can.mockReturnValue(true)
  mocks.auth = reactive({ currentUser: { id: 'U', identity: { employment_epoch: 1 } }, authorizationVersion: 1, can: mocks.can })
  vi.mocked(cartonProcurementApi.listOrders).mockResolvedValue([order(1), order(2), order(3, { customer_code: 'OTHER' }), order(4, { supplier_id: 'OTHER' }), order(5, { status: 'LOCKED' })])
})
async function ready() {
  const w = mount(Component, { props: { source: order(1) } }); await flushPromises()
  await w.get('[aria-label="合单选择 ORD-2"]').setValue(true)
  await w.get('[aria-label="合单新合同号"]').setValue('NEW-1')
  return w
}
describe('existing-order contract merge', () => {
  it('selects eligible existing orders and sends only their revisions and the new contract', async () => {
    vi.mocked(mergeOrderContract).mockResolvedValue([])
    const w = await ready()
    expect(w.findAll('input[type="checkbox"]')).toHaveLength(2)
    await w.get('form').trigger('submit'); await flushPromises()
    expect(mergeOrderContract).toHaveBeenCalledWith(expect.objectContaining({ contract_no: 'NEW-1', expected_revisions: { 'ORD-1': 1, 'ORD-2': 2 } }))
    expect(w.get('[role="status"]').text()).toContain('原需求数量和订单编号保留')
    expect(localStorage.getItem(mergeStorageKey('U', 1, 'huaxing'))).toBeNull()
    w.unmount()
  })
  it('persists uncertain outcomes and replays the exact request after reopening', async () => {
    vi.mocked(mergeOrderContract).mockRejectedValueOnce(new Error('网络中断')).mockResolvedValueOnce([])
    const w = await ready(); await w.get('form').trigger('submit'); await flushPromises()
    const first = JSON.parse(JSON.stringify(vi.mocked(mergeOrderContract).mock.calls[0]![0]))
    expect(w.get('[role="alert"]').text()).toContain('已保留原请求'); w.unmount()
    const restored = mount(Component, { props: { source: order(2) } }); await flushPromises()
    expect(restored.get<HTMLInputElement>('[aria-label="合单新合同号"]').element.matches(':disabled')).toBe(true)
    await restored.get('form').trigger('submit'); await flushPromises()
    expect(vi.mocked(mergeOrderContract).mock.calls[1]![0]).toEqual(first)
    restored.unmount()
  })
  it('rejects a stale selection and requires refreshed candidates', async () => {
    vi.mocked(mergeOrderContract).mockRejectedValue(Object.assign(new Error('订单已变化'), { response: { status: 409 } }))
    const w = await ready(); await w.get('form').trigger('submit'); await flushPromises()
    expect(w.findAll('input[type="checkbox"]')).toHaveLength(0)
    expect(localStorage.getItem(mergeStorageKey('U', 1, 'huaxing'))).toBeNull()
    expect(w.get('[role="alert"]').text()).toContain('刷新候选订单'); w.unmount()
  })
  it('clears protected candidates on identity change and discards late results', async () => {
    let resolve!: (orders: CartonOrderResponse[]) => void
    vi.mocked(cartonProcurementApi.listOrders).mockReturnValueOnce(new Promise(done => { resolve = done }))
    const w = mount(Component, { props: { source: order(1) } })
    mocks.auth.currentUser = undefined; await flushPromises()
    resolve([order(1), order(2)]); await flushPromises()
    expect(w.findAll('input[type="checkbox"]')).toHaveLength(0)
    expect(mergeOrderContract).not.toHaveBeenCalled(); w.unmount()
  })
  it('does not send if the request cannot be durably retained', async () => {
    const w = await ready()
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('full') })
    await w.get('form').trigger('submit'); await flushPromises()
    expect(mergeOrderContract).not.toHaveBeenCalled()
    expect(w.get('[role="alert"]').text()).toContain('尚未提交')
    spy.mockRestore(); w.unmount()
  })
})
