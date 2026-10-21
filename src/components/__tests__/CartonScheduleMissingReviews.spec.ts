import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import Component from '../CartonScheduleMissingReviews.vue'
import { cartonScheduleCoverageApi as api } from '@/api/cartonScheduleCoverage'
import { coverageWorkspace, missingCase } from './cartonScheduleCoverageFixture'

vi.mock('@/lib/http', () => ({ http: {}, getApiErrorMessage: (cause: Error) => cause.message }))
vi.mock('@/api/cartonScheduleCoverage', async original => ({ ...await original<typeof import('@/api/cartonScheduleCoverage')>(), cartonScheduleCoverageApi: { workspace: vi.fn(), detail: vi.fn(), review: vi.fn() } }))
const props = { factoryId: 'huaxing', customerCode: 'DICKIE', viewerKey: 'actor-v1', search: 'CONTRACT1' }
const button = (w: ReturnType<typeof mount>, label: string) => w.findAll('button').find(item => item.text() === label)!
beforeEach(() => { vi.resetAllMocks(); vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] }); vi.mocked(api.workspace).mockResolvedValue(coverageWorkspace()); vi.mocked(api.detail).mockResolvedValue(missingCase()); vi.mocked(api.review).mockResolvedValue({ ...missingCase(), status: 'NO_LONGER_REQUIRED', revision: 3 }) })
afterEach(() => vi.useRealTimers())
it('reads the exact server-filtered queue and retains repeated original rows without merging quantities or creating fake current rows', async () => {
  vi.mocked(api.detail).mockResolvedValue({ ...missingCase(), current_order_ids: ['ORDER-CURRENT'], current_manual_marked: false, current_sources: [{ batch_id: 'OLD1', source_sheet: 'ITEM', source_row: 3, current_order_ids: ['ORDER-CURRENT'], current_manual_marked: false, manual_review_required: true }] })
  const w = mount(Component, { props }); await flushPromises()
  expect(api.workspace).toHaveBeenCalledWith('huaxing', { customer_code: 'DICKIE', status: 'PENDING', keyword: 'CONTRACT1', limit: 20, offset: 0 }, expect.any(AbortSignal))
  expect(w.text()).toContain('2 行原始记录'); expect(w.text()).toContain('不能沿旧来源新建或标记已下单')
  await button(w, '查看与核实').trigger('click'); await flushPromises()
  expect(w.text()).toContain('原数量 4'); expect(w.text()).toContain('原数量 7'); expect(w.text()).not.toContain('原数量 11')
  expect(w.text()).toContain('现存显式关联订单 ORDER-CURRENT · 当前人工已下单 无')
  expect(w.get('[aria-label="当前逐行来源证据"]').text()).toContain('当前来源 ITEM 第 3 行 · 现存订单 ORDER-CURRENT · 人工已下单 无（需求变化待复核）')
  expect(w.text()).toContain('原导入快照记录过人工已下单依据，请查看当前标记状态')
  await button(w, '查看本次全量比较与排除依据').trigger('click')
  expect(w.emitted('source')).toEqual([['FULL1']])
  await w.findAll('button').find(item => item.text() === '查看此行原来源')!.trigger('click')
  expect(w.emitted('source')!.at(-1)).toEqual(['OLD1']); w.unmount()
})
it('records an explicit no-longer-required conclusion using current evidence without cancelling procurement and supports reasoned reopening', async () => {
  const w = mount(Component, { props }); await flushPromises(); await button(w, '查看与核实').trigger('click'); await flushPromises()
  await w.get('[aria-label="缺行核实结论"]').setValue('NO_LONGER_REQUIRED')
  await w.get('[aria-label="缺行核实原因"]').setValue('已与业务核实不再需要')
  await w.get('form').trigger('submit'); await flushPromises()
  expect(api.review).toHaveBeenCalledWith('MISSING1', expect.objectContaining({ factory_id: 'huaxing', expected_revision: 2, source_fingerprint: 'f'.repeat(64), decision: 'NO_LONGER_REQUIRED', reason: '已与业务核实不再需要' }), expect.any(AbortSignal))
  expect(w.emitted('changed')).toEqual([['DICKIE']])
  expect(w.get('[role="status"]').text()).toContain('正式采购单、需求、人工已下单标记和库存均未自动变更')
  expect(w.findAll('[aria-label="缺行核实结论"] option').map(item => item.attributes('value'))).toEqual(['REOPEN'])
  await w.get('[aria-label="缺行核实原因"]').setValue('原人工结论有误重新核查')
  await w.get('form').trigger('submit'); await flushPromises()
  expect(vi.mocked(api.review).mock.calls[1]![1]).toMatchObject({ expected_revision: 3, decision: 'REOPEN' }); w.unmount()
})
it('preserves evidence and retry identity after stale/uncertain failures, but clears it for another actor', async () => {
  vi.mocked(api.review).mockRejectedValue(new Error('核实版本已变化，请刷新'))
  const w = mount(Component, { props }); await flushPromises(); await button(w, '查看与核实').trigger('click'); await flushPromises()
  await w.get('[aria-label="缺行核实原因"]').setValue('核对业务原始排期凭证')
  await w.get('form').trigger('submit'); await flushPromises()
  const first = vi.mocked(api.review).mock.calls[0]![1]
  expect(w.get<HTMLTextAreaElement>('[aria-label="缺行核实原因"]').element.value).toBe('核对业务原始排期凭证')
  await w.get('form').trigger('submit'); await flushPromises()
  expect(vi.mocked(api.review).mock.calls[1]![1]).toEqual(first)
  await w.setProps({ viewerKey: 'actor-v2' }); await flushPromises()
  expect(w.find('form').exists()).toBe(false); w.unmount()
})
it('makes superseded cases and forbidden viewers read-only, while retaining changed baseline evidence separately from the original snapshot', async () => {
  vi.mocked(api.detail).mockResolvedValue({ ...missingCase(), status: 'SUPERSEDED', can_review: false, basis_changed: true, effective_source_rows: [{ batch_id: 'OLDER', source_sheet: 'ITEM2', source_row: 8, quantity: 2 }] })
  const w = mount(Component, { props }); await flushPromises(); await button(w, '查看与核实').trigger('click'); await flushPromises()
  expect(w.text()).toContain('已有新版核实项（历史只读）'); expect(w.find('form').exists()).toBe(false)
  expect(w.text()).toContain('原比较基线已变化'); expect(w.text()).toContain('有效来源 ITEM2 第 8 行 · 数量 2'); expect(w.text()).toContain('原数量 7')
  expect(api.review).not.toHaveBeenCalled(); w.unmount()
})
it('does not claim an empty queue on errors and discards retired factory detail results', async () => {
  vi.mocked(api.workspace).mockRejectedValueOnce(new Error('读取失败'))
  const w = mount(Component, { props }); await flushPromises()
  expect(w.get('[role="alert"]').text()).toContain('读取失败'); expect(w.text()).not.toContain('当前没有待核实缺行')
  await button(w, '刷新核实清单').trigger('click'); await flushPromises()
  let done!: (value: ReturnType<typeof missingCase>) => void
  vi.mocked(api.detail).mockImplementationOnce(() => new Promise(resolve => { done = resolve }))
  await button(w, '查看与核实').trigger('click'); await flushPromises()
  const signal = vi.mocked(api.detail).mock.calls[0]![2]!
  vi.mocked(api.workspace).mockResolvedValue({ ...coverageWorkspace(), factory_id: 'huadeng', missing: { ...coverageWorkspace().missing, items: [], total: 0 } })
  await w.setProps({ factoryId: 'huadeng' }); await flushPromises(); done(missingCase()); await flushPromises()
  expect(signal.aborted).toBe(true); expect(w.find('[aria-label="缺行核实详情"]').exists()).toBe(false); w.unmount()
})
