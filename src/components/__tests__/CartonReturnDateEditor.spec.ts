import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { reactive } from 'vue'
import Component from '../CartonReturnDateEditor.vue'
import { cartonSupplierReturnsApi as returns } from '@/api/cartonSupplierReturns'
import { supplierSettlementApi as settlement } from '@/api/cartonSupplierSettlement'
import { row } from './cartonReturnFixture'

vi.mock('@/api/cartonSupplierReturns', () => ({ cartonSupplierReturnsApi: { detail: vi.fn() } }))
vi.mock('@/api/cartonSupplierSettlement', () => ({ supplierSettlementApi: { correctReturnDate: vi.fn() } }))
vi.mock('@/lib/http', () => ({ getApiErrorMessage: (cause: Error) => cause.message }))
beforeEach(() => { vi.resetAllMocks(); vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-10-20T12:00:00Z')); vi.mocked(returns.detail).mockResolvedValue({ ...row(), allowed_actions: ['CORRECT_DATE'] }) })
afterEach(() => vi.useRealTimers())
it('fetches independent evidence and posts the exact reasoned date version, preserving uncertain retry identity and original cash', async () => {
  const detail = { ...row(), cash_confirmed_amount: '6.00', allowed_actions: ['CORRECT_DATE'] }
  vi.mocked(returns.detail).mockResolvedValue(detail)
  vi.mocked(settlement.correctReturnDate).mockRejectedValueOnce(new Error('先说明原因重开2026-09月结'))
  const w = mount(Component, { props: { factoryId: 'huaxing', movementId: 'M1', viewerKey: 'admin-v1' } }); await flushPromises()
  await w.get('[aria-label="更正后的实际退货日期"]').setValue('2026-09-30')
  await w.get('[aria-label="实际退货日期更正原因"]').setValue('已核实原始交接单')
  await w.get('form').trigger('submit'); await flushPromises()
  const body = vi.mocked(settlement.correctReturnDate).mock.calls[0]![1]
  expect(body).toMatchObject({ factory_id: 'huaxing', expected_evidence_revision: 1, expected_evidence_fingerprint: 'd'.repeat(64), return_date: '2026-09-30', reason: '已核实原始交接单' })
  expect(w.get('[role="alert"]').text()).toContain('重开2026-09')
  expect(w.get<HTMLInputElement>('[aria-label="更正后的实际退货日期"]').element.value).toBe('2026-09-30')
  await w.get('form').trigger('submit'); await flushPromises()
  expect(vi.mocked(settlement.correctReturnDate).mock.calls[1]![1]).toEqual(body)
  expect(w.emitted('saved')).toHaveLength(1)
  expect(detail.cash_confirmed_amount).toBe('6.00'); expect(detail.posting_date).toBe('2026-10-02')
  w.unmount()
})
it('fails closed when authority or date evidence is missing', async () => {
  vi.mocked(returns.detail).mockResolvedValue({ ...row(), allowed_actions: [] })
  const w = mount(Component, { props: { factoryId: 'huaxing', movementId: 'M1' } }); await flushPromises()
  expect(w.find('form').exists()).toBe(false); expect(w.get('[role="alert"]').text()).toContain('不可更正日期')
  expect(settlement.correctReturnDate).not.toHaveBeenCalled(); w.unmount()
})
it('clears old evidence on a viewer change and discards a retired detail response', async () => {
  let done!: (value: ReturnType<typeof row>) => void
  vi.mocked(returns.detail).mockImplementationOnce(() => new Promise(resolve => { done = resolve }))
  const state = reactive({ factoryId: 'huaxing', movementId: 'M1', viewerKey: 'admin-v1' })
  const w = mount(Component, { props: state }); await flushPromises()
  const signal = vi.mocked(returns.detail).mock.calls[0]![3]!
  vi.mocked(returns.detail).mockRejectedValueOnce(new Error('权限已变化'))
  await w.setProps({ viewerKey: 'admin-v2' }); await flushPromises()
  done({ ...row(), allowed_actions: ['CORRECT_DATE'] }); await flushPromises()
  expect(signal.aborted).toBe(true); expect(w.find('form').exists()).toBe(false)
  expect(w.text()).toContain('权限已变化'); w.unmount()
})
