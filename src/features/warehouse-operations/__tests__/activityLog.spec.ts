import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DOMWrapper, flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { reactive, ref } from 'vue'
import { parseDate } from '@internationalized/date'
import DateRangeFilter from '@/components/DateRangeFilter.vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { WarehouseDocument, WarehouseOperationsWorkspace } from '@/api/warehouseOperations'
import ActivityLog from '../FabricActivityLog.vue'
import { activitySummary, filterActivity, operationTime, type ActivityFilters } from '../activityLog'
import { activitySearchKey } from '../inventorySearch'

const api = vi.hoisted(() => ({ workspace: vi.fn(), post: vi.fn() }))
vi.mock('@/api/warehouseOperations', () => ({ warehouseOperationsApi: api }))
let auth = reactive({ currentUser: { id: 'one' }, authorizationVersion: 1 })
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))
const row = (id: string, values: Partial<WarehouseDocument> = {}): WarehouseDocument => ({
  id, kind: 'ISSUE', sequence: 1, business_date: '2026-10-01', occurred_at: '2026-10-13T09:00:00+08:00', actor_name: '张三',
  data: { kind: 'ISSUE', quantity: '2', unit: '码', item_name: '测试布料', item_code: id, source_no: '送货01', reason: '核对依据' } as WarehouseDocument['data'], ...values,
})
const defaults: ActivityFilters = { search: '', from: '', to: '', kind: '', actor: '', state: '', dateField: 'OPERATION', sort: 'DESC' }
const workspace = (documents: WarehouseDocument[], originals: WarehouseDocument[] = []): WarehouseOperationsWorkspace => ({ revision: 1, stock: [], documents, original_receipts: originals, permissions: { read: true, operate: true, quality: false, correct: true } })
let wrapper: VueWrapper | undefined
const search = ref('')
async function open() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div/>' } }] })
  await router.push('/'); await router.isReady()
  wrapper = mount(ActivityLog, { attachTo: document.body, global: { plugins: [router], provide: { [activitySearchKey as symbol]: { search, submitted: ref(0), active: ref(true) } } } })
  await flushPromises()
  return wrapper
}
beforeEach(() => { vi.clearAllMocks(); search.value = ''; auth = reactive({ currentUser: { id: 'one' }, authorizationVersion: 1 }) })
afterEach(() => { wrapper?.unmount(); document.body.innerHTML = '' })

describe('activity time and evidence', () => {
  it('sorts by actual operation time, normalizes Beijing dates and keeps unknown times last', () => {
    expect(operationTime('2026-10-12T17:00:00Z')).toBe('2026-10-13 01:00:00')
    expect(operationTime('2026-10-13T09:00:00')).toBe('2026-10-13 09:00:00')
    expect(operationTime('invalid')).toBe('')
    const rows = [row('old', { business_date: '2026-10-12', occurred_at: '2026-10-12T12:00:00+08:00' }), row('new'), row('unknown', { occurred_at: '' })]
    expect(filterActivity(rows, defaults).map(r => r.id)).toEqual(['new', 'old', 'unknown'])
    expect(filterActivity(rows, { ...defaults, sort: 'ASC' }).map(r => r.id)).toEqual(['old', 'new', 'unknown'])
    expect(filterActivity(rows, { ...defaults, from: '2026-10-13', to: '2026-10-13' }).map(r => r.id)).toEqual(['new'])
    expect(filterActivity(rows, { ...defaults, dateField: 'BUSINESS', from: '2026-10-12' }).map(r => r.id)).toEqual(['old'])
  })
  it('combines type, actor, status, text and inclusive dates without hiding reversed evidence', () => {
    const reversed = row('reversed', { reversed: true })
    const filters = { ...defaults, kind: 'ISSUE', actor: '张三', state: 'REVERSED', search: '核对依据', from: '2026-10-13', to: '2026-10-13' }
    expect(filterActivity([row('active'), reversed, row('other', { reversed: true, actor_name: '李四' })], filters)).toEqual([reversed])
    expect(filterActivity([reversed], { ...filters, from: '2026-10-14' })).toEqual([])
  })
  it('preserves zero counts and displays recorded location changes without inventing a balance', () => {
    const record = row('count', { kind: 'STOCKTAKE' })
    Object.assign(record.data, { book_quantity: '2', actual_quantity: '0', quantity: '-2' })
    expect(activitySummary(record)).toBe('账面 2 → 实盘 0 码；差异 -2')
    record.kind = 'LOCATION_BIND'; record.data.location = 'A / A2'
    expect(activitySummary(record)).toBe('仓位 未记录 → A / A2；数量不变')
    record.kind = 'QUALITY'; record.data.quality_status = 'QUALIFIED'
    expect(activitySummary(record)).toBe('历史质检：未记录 → 合格')
  })
})

describe('read-only fabric activity page', () => {
  it('combines originals, filters before paging and resets the shell search with filters', async () => {
    api.workspace.mockResolvedValue(workspace(Array.from({ length: 51 }, (_, i) => row(`R${i}`)), [row('original', { kind: 'RECEIPT', read_only: true, actor_name: '李四' })]))
    const view = await open()
    expect(view.findAll('tbody tr')).toHaveLength(50)
    await view.findAll('button').find(b => b.text() === '下一页')!.trigger('click')
    expect(view.findAll('tbody tr')).toHaveLength(2)
    await view.get('[aria-label="日志经办人"]').setValue('李四')
    expect(view.findAll('tbody tr')).toHaveLength(1)
    expect(view.get('tbody').text()).toContain('采购实收入库 · 批次')
    expect(view.get('.activity-footer').text()).toContain('显示 1–1')
    search.value = '不存在'; await flushPromises()
    expect(view.text()).toContain('没有符合条件的记录')
    await view.findAll('button').find(b => b.text() === '重置筛选')!.trigger('click')
    expect(search.value).toBe(''); expect(view.findAll('tbody tr')).toHaveLength(50)
    view.getComponent(DateRangeFilter).vm.$emit('update:modelValue', { start: parseDate('2026-10-13'), end: parseDate('2026-10-13') }); await flushPromises()
    expect(view.findAll('tbody tr')).toHaveLength(50)
    await view.get('[aria-label="日志日期口径"]').setValue('BUSINESS')
    expect(view.text()).toContain('没有符合条件的记录')
    view.getComponent(DateRangeFilter).vm.$emit('update:modelValue', { start: undefined, end: undefined }); await flushPromises()
    expect(view.findAll('tbody tr')).toHaveLength(50)
    expect(api.post).not.toHaveBeenCalled()
  })
  it('opens read-only correction evidence and its related original without offering posting', async () => {
    const correction = row('correction', { kind: 'CORRECTION', sequence: 2 })
    Object.assign(correction.data, { original_id: 'original', reversed_kind: 'ISSUE' })
    api.workspace.mockResolvedValue(workspace([correction, row('original', { reversed: true })]))
    const view = await open()
    expect(view.findAll('tbody button').map(b => b.text())).toEqual(['详情', '详情'])
    await view.get('tbody button').trigger('click'); await flushPromises()
    const body = new DOMWrapper(document.body)
    expect(body.get('[role=dialog]').text()).toContain('核对依据')
    expect(body.get('[role=dialog] a').attributes('href')).toContain('view=movements')
    auth.currentUser = { id: 'one' }; await flushPromises()
    expect(api.workspace).toHaveBeenCalledTimes(1)
    expect(body.get('[role=dialog]').text()).toContain('核对依据')
    await body.findAll('button').find(b => b.text() === '查看关联原单')!.trigger('click')
    expect(body.get('[role=dialog]').text()).toContain('原单已冲销，原记录保留')
    expect(api.post).not.toHaveBeenCalled()
  })
  it('clears records on failed refresh and ignores a response from the prior identity', async () => {
    let resolveOld!: (value: WarehouseOperationsWorkspace) => void
    api.workspace.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }))
    const view = await open()
    api.workspace.mockResolvedValueOnce(workspace([row('current', { actor_name: '当前用户' })]))
    auth.currentUser.id = 'two'; await flushPromises()
    resolveOld(workspace([row('stale', { actor_name: '旧用户' })])); await flushPromises()
    expect(view.get('tbody').text()).toContain('当前用户')
    expect(view.text()).not.toContain('旧用户')
    api.workspace.mockRejectedValueOnce(new Error('读取失败'))
    await view.findAll('button').find(b => b.text() === '刷新')!.trigger('click'); await flushPromises()
    expect(view.find('tbody').exists()).toBe(false)
    expect(view.find('[role=alert]').exists()).toBe(true)
  })
})
