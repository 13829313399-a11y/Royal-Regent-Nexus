import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import Component from '../CartonScheduleCoverageOverview.vue'
import { cartonScheduleCoverageApi as api } from '@/api/cartonScheduleCoverage'
import { coverageCustomer, coverageWorkspace } from './cartonScheduleCoverageFixture'

vi.mock('@/lib/http', () => ({ http: {}, getApiErrorMessage: (cause: Error) => cause.message }))
vi.mock('@/api/cartonScheduleCoverage', async original => ({ ...await original<typeof import('@/api/cartonScheduleCoverage')>(), cartonScheduleCoverageApi: { workspace: vi.fn() } }))
beforeEach(() => {
  vi.resetAllMocks()
  const row = coverageCustomer()
  vi.mocked(api.workspace).mockResolvedValue({ ...coverageWorkspace(), customers: [row, { ...row, customer_code: 'EMPTY', customer_name: '尚无导入客户', latest_import: null, full_coverage: null, pending_count: 0, excluded_count: 0 }, { ...row, customer_code: 'OLD', customer_name: '停用客户', status: 'INACTIVE' }, { ...row, customer_code: '__UNBOUND__', customer_name: '未绑定客户', latest_import: { ...row.latest_import!, scope_mode: 'UNDECLARED', as_of_date: null }, full_coverage: null }] })
})
it('shows the complete server customer summary even when the missing result page is one row, without inventing continuous coverage', async () => {
  const w = mount(Component, { props: { factoryId: 'huaxing', viewerKey: 'u1' } }); await flushPromises()
  expect(api.workspace).toHaveBeenCalledWith('huaxing', { status: 'PENDING', limit: 1, offset: 0 }, expect.any(AbortSignal))
  expect(w.text()).toContain('显示 4 / 4 个客户'); expect(w.text()).toContain('尚无导入客户'); expect(w.text()).toContain('已停用 · 只读')
  expect(w.text()).toContain('范围未声明'); expect(w.text()).toContain('未绑定客户，不推断覆盖')
  expect(w.text()).toContain('仅此声明段，不推定其他日期已覆盖'); expect(w.text()).toContain('缺行待核实 1 项')
  await w.findAll('button').find(item => item.text() === '查看原批次排除明细')!.trigger('click')
  expect(w.emitted('source')).toEqual([['FULL1']])
  await w.get('[aria-label="客户覆盖显示范围"]').setValue('NO_IMPORT')
  expect(w.get('tbody').text()).toContain('尚无导入客户'); expect(w.get('tbody').text()).not.toContain('停用客户')
  w.unmount()
})
it('keeps client summary search separate from missing rows and preserves exact customer navigation', async () => {
  const w = mount(Component, { props: { factoryId: 'huaxing', search: 'EMPTY' } }); await flushPromises()
  expect(w.get('tbody').findAll('tr')).toHaveLength(1)
  await w.findAll('button').find(item => item.text() === '排期明细')!.trigger('click')
  expect(w.emitted('customer')).toEqual([['EMPTY']])
  await w.findAll('button').find(item => item.text() === '缺行核实')!.trigger('click')
  expect(w.emitted('missing')).toEqual([['EMPTY']]); w.unmount()
})
it('reports errors without a false empty total and discards another viewer response', async () => {
  let done!: (value: ReturnType<typeof coverageWorkspace>) => void
  vi.mocked(api.workspace).mockImplementationOnce(() => new Promise(resolve => { done = resolve }))
  const w = mount(Component, { props: { factoryId: 'huaxing', viewerKey: 'u1' } }); await flushPromises()
  const signal = vi.mocked(api.workspace).mock.calls[0]![2]!
  vi.mocked(api.workspace).mockRejectedValueOnce(new Error('读取权限已变化'))
  await w.setProps({ viewerKey: 'u2' }); await flushPromises(); done(coverageWorkspace()); await flushPromises()
  expect(signal.aborted).toBe(true); expect(w.get('[role="alert"]').text()).toContain('读取权限已变化')
  expect(w.find('table').exists()).toBe(false); expect(w.text()).not.toContain('显示 0'); w.unmount()
})
