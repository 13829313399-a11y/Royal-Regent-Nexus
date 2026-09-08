import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import CartonStocktakeWorkspace from '../CartonStocktakeWorkspace.vue'

const mocks = vi.hoisted(() => ({ list: vi.fn(), detail: vi.fn(), create: vi.fn(), act: vi.fn(), balances: vi.fn(), user: { id: 'counter' }, can: vi.fn(() => true) }))
vi.mock('@/api/cartonStocktake', () => ({ cartonStocktakeApi: mocks }))
vi.mock('@/api/cartonProcurement', () => ({ cartonProcurementApi: { listInventoryBalances: mocks.balances } }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ currentUser: mocks.user, can: mocks.can }) }))
vi.mock('vue-router', () => ({ onBeforeRouteLeave: vi.fn(), onBeforeRouteUpdate: vi.fn() }))
const balance = { factory_id: 'huaxing', customer_code: 'C', customer_name: '客户', contract_no: 'CONTRACT', item_no: 'ITEM', packaging_type: '外箱', paper_quality: 'A33', specification: '1*1*1', unit: '个', balance: '100', latest_location: 'A', latest_movement_id: 'M1' }
function detail(status = 'DRAFT') {
  return { id: 'PD-1', factory_id: 'huaxing', status, revision: 1, ledger_token: 'token-1', basis_changed: false,
    created_by: 'counter', created_by_name: '仓管', created_at: '2026-09-07T10:00:00+08:00',
    submitted_by: status === 'DRAFT' ? '' : 'counter', submitted_by_name: '', submitted_at: '', reviewed_by: '', reviewed_by_name: '', reviewed_at: '', note: '', cutoff_at: '2026-09-07T10:00:00+08:00', events: [],
    lines: [{ ...balance, id: 'L1', initial_quantity: '100', count_book_quantity: '100', current_quantity: '100', actual_quantity: null as string | null, difference: null, reason: '', location_changed: false, movement_id: '' }],
  }
}
function button(wrapper: ReturnType<typeof mount>, label: string) {
  const found = wrapper.findAll('button').find(item => item.text() === label)
  if (!found) throw new Error(`Missing button ${label}`)
  return found
}
async function open() {
  const wrapper = mount(CartonStocktakeWorkspace, { props: { factoryId: 'huaxing' } })
  await flushPromises()
  await button(wrapper, '查看 / 处理').trigger('click'); await flushPromises()
  return wrapper
}
beforeEach(() => {
  vi.clearAllMocks(); mocks.user.id = 'counter'; mocks.can.mockReturnValue(true)
  mocks.balances.mockResolvedValue([balance]); mocks.list.mockResolvedValue([detail()])
  mocks.detail.mockResolvedValue(detail()); mocks.create.mockResolvedValue(detail()); mocks.act.mockResolvedValue(detail())
})
describe('库存盘点工作台', () => {
  it('opens the ledger selection directly for counting without selecting again', async () => {
    const wrapper = mount(CartonStocktakeWorkspace, { props: { factoryId: 'huaxing', initialPositionKeys: ['M1'] } })
    await flushPromises()
    expect(mocks.create).toHaveBeenCalledExactlyOnceWith('huaxing', ['M1'])
    expect(wrapper.find('[aria-label="实盘数量 L1"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('生成盘点单')
    await button(wrapper, '盘点单列表').trigger('click'); await flushPromises()
    expect(mocks.create).toHaveBeenCalledTimes(1)
    expect(wrapper.get('[aria-label="全选盘点筛选结果"]').element.closest('th')).not.toBeNull()
  })
  it('does not create from a stale selection or while browsing without a selection', async () => {
    let wrapper = mount(CartonStocktakeWorkspace, { props: { factoryId: 'huaxing', initialPositionKeys: ['missing'] } })
    await flushPromises()
    expect(mocks.create).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('所选库存已变化')
    wrapper.unmount()
    wrapper = mount(CartonStocktakeWorkspace, { props: { factoryId: 'huaxing' } })
    await flushPromises()
    expect(mocks.create).not.toHaveBeenCalled()
  })
  it('does not start a draft after leaving during the initial load', async () => {
    let resolve!: (value: typeof balance[]) => void
    mocks.balances.mockReturnValue(new Promise(res => { resolve = res }))
    const wrapper = mount(CartonStocktakeWorkspace, { props: { factoryId: 'huaxing', initialPositionKeys: ['M1'] } })
    wrapper.unmount()
    resolve([balance]); await flushPromises()
    expect(mocks.create).not.toHaveBeenCalled()
  })
  it('prefills cancellation without enabling an unexplained return for recount', async () => {
    mocks.detail.mockResolvedValue(detail('SUBMITTED'))
    const wrapper = await open()
    expect(wrapper.get<HTMLInputElement>('[aria-label="盘点取消原因"]').element.value).toBe('取消本次盘点')
    expect(wrapper.get<HTMLInputElement>('[aria-label="盘点退回原因"]').element.value).toBe('')
    expect(button(wrapper, '退回重盘').attributes('disabled')).toBeDefined()
    await wrapper.get('[aria-label="盘点取消原因"]').setValue('本次盘点范围选错')
    await button(wrapper, '取消盘点').trigger('click'); await flushPromises()
    expect(mocks.act).toHaveBeenCalledWith('PD-1', expect.objectContaining({ action: 'CANCEL', reason: '本次盘点范围选错' }))
  })
  it('shows balances but disables creation when the backend feature is not enabled', async () => {
    mocks.list.mockRejectedValue({ response: { status: 404 } })
    const wrapper = mount(CartonStocktakeWorkspace, { props: { factoryId: 'huaxing' } })
    await flushPromises()
    expect(wrapper.text()).toContain('盘点服务尚未启用')
    expect(wrapper.text()).toContain('CONTRACT')
    await wrapper.findAll('input[type=checkbox]')[0]!.setValue(true)
    expect(button(wrapper, '生成盘点单').attributes('disabled')).toBeDefined()
  })
  it('selects filtered inventory and creates a scoped document', async () => {
    mocks.balances.mockResolvedValue([balance, { ...balance, customer_code: 'OTHER', customer_name: '其他客户', latest_movement_id: 'M2', latest_location: 'B' }])
    const wrapper = mount(CartonStocktakeWorkspace, { props: { factoryId: 'huaxing' } })
    await flushPromises(); await wrapper.get('[aria-label="盘点仓位"]').setValue('A')
    await wrapper.findAll('input[type=checkbox]')[0]!.setValue(true)
    await button(wrapper, '生成盘点单').trigger('click'); await flushPromises()
    expect(mocks.create).toHaveBeenCalledWith('huaxing', ['M1'])
  })
  it('preserves blank as null and submits explicit zero only after acknowledgment', async () => {
    const wrapper = await open()
    await button(wrapper, '保存草稿').trigger('click'); await flushPromises()
    expect(mocks.act.mock.calls[0]![1].lines[0].actual_quantity).toBeNull()
    expect(button(wrapper, '提交主管复核').attributes('disabled')).toBeDefined()
    await wrapper.get('[aria-label="实盘数量 L1"]').setValue('0')
    await wrapper.get('[aria-label="差异原因 L1"]').setValue('实际已用完')
    await wrapper.get('input[type=checkbox]').setValue(true)
    await button(wrapper, '提交主管复核').trigger('click'); await flushPromises()
    expect(mocks.act.mock.lastCall![1]).toMatchObject({ action: 'SUBMIT', ledger_token: 'token-1', cutoff_acknowledged: true, lines: [{ id: 'L1', actual_quantity: '0', reason: '实际已用完' }] })
  })
  it('does not retry conflicts; refresh keeps inputs and requires another acknowledgment', async () => {
    const wrapper = await open()
    await wrapper.get('[aria-label="实盘数量 L1"]').setValue('98')
    await wrapper.get('[aria-label="差异原因 L1"]').setValue('盘亏')
    await wrapper.get('input[type=checkbox]').setValue(true)
    mocks.act.mockRejectedValueOnce(new Error('conflict'))
    await button(wrapper, '提交主管复核').trigger('click'); await flushPromises()
    expect(mocks.act).toHaveBeenCalledTimes(1)
    const refreshed = detail(); refreshed.ledger_token = 'token-2'; refreshed.basis_changed = true; refreshed.lines[0]!.current_quantity = '90'
    mocks.detail.mockResolvedValue(refreshed)
    await button(wrapper, '刷新并重新核对').trigger('click'); await flushPromises()
    expect(wrapper.get<HTMLInputElement>('[aria-label="实盘数量 L1"]').element.value).toBe('98')
    expect(wrapper.text()).toContain('原实盘数字仅供参考')
    expect(wrapper.text()).toContain('上次账面 100')
    expect(button(wrapper, '提交主管复核').attributes('disabled')).toBeDefined()
    expect(mocks.act).toHaveBeenCalledTimes(1)
  })
  it('shows stale saved basis immediately when reopening a draft', async () => {
    const saved = detail(); saved.basis_changed = true; saved.lines[0]!.actual_quantity = '98'
    mocks.detail.mockResolvedValue(saved)
    const wrapper = await open()
    expect(wrapper.text()).toContain('原实盘数字仅供参考')
    expect(button(wrapper, '提交主管复核').attributes('disabled')).toBeDefined()
  })
  it('separates creator and supervisor review controls', async () => {
    mocks.detail.mockResolvedValue(detail('SUBMITTED'))
    let wrapper = await open()
    expect(wrapper.text()).toContain('等待另一位有复核权限的主管处理')
    expect(wrapper.findAll('button').some(item => item.text() === '复核并差额入账')).toBe(false)
    wrapper.unmount(); mocks.user.id = 'manager'; wrapper = await open()
    expect(button(wrapper, '复核并差额入账').exists()).toBe(true)
    expect(wrapper.find('[aria-label="实盘数量 L1"]').exists()).toBe(false)
  })
  it('shows selections hidden by search and clears failed status results', async () => {
    const wrapper = mount(CartonStocktakeWorkspace, { props: { factoryId: 'huaxing' } })
    await flushPromises()
    await wrapper.get('[aria-label="全选盘点筛选结果"]').setValue(true)
    await wrapper.get('[aria-label="盘点库存搜索"]').setValue('missing')
    expect(wrapper.get('[aria-label="批量已选范围"]').text()).toContain('其中 1 条不在当前筛选内')
    await button(wrapper, '清空选择').trigger('click')
    expect(wrapper.get('[aria-label="批量已选范围"]').text()).toContain('已选 0')
    mocks.list.mockRejectedValue(new Error('查询失败'))
    await wrapper.get('[aria-label="盘点记录状态"]').setValue('POSTED'); await flushPromises()
    expect(mocks.list).toHaveBeenLastCalledWith('huaxing', 0, 'POSTED')
    expect(wrapper.text()).not.toContain('PD-1')
    wrapper.unmount()
  })

})
