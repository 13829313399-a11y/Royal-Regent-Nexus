import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Component from '../CartonOpeningInventoryBatches.vue'
import type { OpeningBatchReversalPreview } from '@/api/cartonProcurement'

const api = vi.hoisted(() => ({ listOpeningInventoryBatches: vi.fn(), previewOpeningBatchReversal: vi.fn(), reverseOpeningBatch: vi.fn() }))
vi.mock('@/api/cartonProcurement', () => ({ cartonProcurementApi: api }))
const props = { factoryId: 'huaxing', viewerKey: 'admin:1', connected: true, canManage: true }
const batch = { batch_id: 'CHI2-1', filename: '原期初表.xlsx', imported_at: '2026-10-22T09:00:00+08:00',
  actor_name: '管理员', row_count: 2, reversed_count: 0, status: 'ACTIVE' as const, date_from: '2026-03-01', date_to: '2026-05-01' }
function preview(): OpeningBatchReversalPreview {
  return { ...batch, factory_id: 'huaxing', source_fingerprint: 'a'.repeat(64), errors: [], totals: [{ unit: '个', quantity: '30' }],
    rows: [{ movement_id: 'M1', customer_name: '客户', contract_no: 'C1', item_no: 'I1', packaging_type: '外箱', paper_quality: 'A33',
      specification: '12*10*5 in', quantity: '10', unit: '个', unit_price: '2', location: 'A / A1', occurred_at: '2026-03-01T09:00:00+08:00' }] }
}
const result = { factory_id: 'huaxing', batch_id: batch.batch_id, reversed_count: 2, status: 'REVERSED', duplicate: false, movement_ids: ['R1', 'R2'] }
const button = (wrapper: ReturnType<typeof mount>, text: string) => wrapper.findAll('button').find(item => item.text() === text)!
async function opened() {
  const wrapper = mount(Component, { props }); await flushPromises()
  await wrapper.get('[aria-label="预览撤销期初批次 原期初表.xlsx"]').trigger('click'); await flushPromises()
  return wrapper
}

describe('opening batch cancellation', () => {
  beforeEach(() => {
    vi.resetAllMocks(); sessionStorage.clear()
    api.listOpeningInventoryBatches.mockResolvedValue({ factory_id: 'huaxing', total: 1, items: [batch] })
    api.previewOpeningBatchReversal.mockResolvedValue(preview())
    api.reverseOpeningBatch.mockResolvedValue(result)
  })
  it('shows original file and dates, previews every row, then requires explicit review and reason', async () => {
    const wrapper = await opened()
    expect(wrapper.text()).toContain('2026-03-01 ～ 2026-05-01')
    expect(wrapper.text()).toContain('12*10*5 inch')
    expect(api.reverseOpeningBatch).not.toHaveBeenCalled()
    expect(button(wrapper, '确认整批撤销').attributes('disabled')).toBeDefined()
    await wrapper.get('[aria-label="已核对整批撤销"]').setValue(true)
    await wrapper.get('[aria-label="期初整批撤销原因"]').setValue('文件导错了')
    await button(wrapper, '确认整批撤销').trigger('click'); await flushPromises()
    expect(api.reverseOpeningBatch).toHaveBeenCalledWith('CHI2-1', expect.objectContaining({
      factory_id: 'huaxing', expected_fingerprint: 'a'.repeat(64), reason: '文件导错了', request_id: expect.any(String),
    }))
    expect(wrapper.emitted('reversed')).toHaveLength(1)
    expect(wrapper.text()).toContain('共 2 笔')
    expect(wrapper.find('[aria-label="整批撤销预览"]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('blocks the complete operation when one original row has a downstream dependency', async () => {
    const checked = preview(); checked.errors = ['相关纸品已有调仓记录']
    api.previewOpeningBatchReversal.mockResolvedValue(checked)
    const wrapper = await opened()
    expect(wrapper.text()).toContain('本批暂不能整批撤销')
    expect(wrapper.get('[aria-label="已核对整批撤销"]').attributes('disabled')).toBeDefined()
    expect(button(wrapper, '确认整批撤销').attributes('disabled')).toBeDefined()
    expect(api.reverseOpeningBatch).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('retains the identical request across timeout, remount and retry', async () => {
    api.reverseOpeningBatch.mockRejectedValueOnce(new Error('连接中断'))
    const first = await opened()
    await first.get('[aria-label="已核对整批撤销"]').setValue(true)
    await button(first, '确认整批撤销').trigger('click'); await flushPromises()
    const submitted = api.reverseOpeningBatch.mock.calls[0]![1]
    first.unmount()
    const second = await opened()
    expect(second.get('[aria-label="期初整批撤销原因"]').attributes('disabled')).toBeDefined()
    await button(second, '核对并重试原撤销请求').trigger('click'); await flushPromises()
    expect(api.reverseOpeningBatch.mock.calls[1]![1]).toEqual(submitted)
    expect(second.emitted('reversed')).toHaveLength(1)
    second.unmount()
  })
  it('rejects a stale preview and requires fresh verification before another submit', async () => {
    api.reverseOpeningBatch.mockRejectedValueOnce({ isAxiosError: true, response: { status: 409, data: { detail: '库存已变化' } } })
    const wrapper = await opened()
    await wrapper.get('[aria-label="已核对整批撤销"]').setValue(true)
    await button(wrapper, '确认整批撤销').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('请重新预览撤销')
    expect(wrapper.find('[aria-label="整批撤销预览"]').exists()).toBe(false)
    expect(wrapper.emitted('reversed')).toBeUndefined()
    wrapper.unmount()
  })
  it('ignores late preview and confirmation responses after switching factories or accounts', async () => {
    let finish!: (value: OpeningBatchReversalPreview) => void
    api.previewOpeningBatchReversal.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const wrapper = mount(Component, { props }); await flushPromises()
    await wrapper.get('[aria-label="预览撤销期初批次 原期初表.xlsx"]').trigger('click')
    await wrapper.setProps({ factoryId: 'huakang-a' })
    finish(preview()); await flushPromises()
    expect(wrapper.find('[aria-label="整批撤销预览"]').exists()).toBe(false)
    wrapper.unmount()

    const current = await opened()
    let complete!: (value: typeof result) => void
    api.reverseOpeningBatch.mockImplementationOnce(() => new Promise(resolve => { complete = resolve }))
    await current.get('[aria-label="已核对整批撤销"]').setValue(true)
    await button(current, '确认整批撤销').trigger('click')
    await current.setProps({ viewerKey: 'other-user:1' })
    complete(result); await flushPromises()
    expect(current.emitted('reversed')).toBeUndefined()
    expect(current.text()).not.toContain('已整批撤销，共')
    current.unmount()
  })
  it('makes no requests when current permissions or backend connectivity are absent', async () => {
    const wrapper = mount(Component, { props: { ...props, canManage: false } }); await flushPromises()
    expect(api.listOpeningInventoryBatches).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('需要本厂库存操作权限')
    await wrapper.setProps({ canManage: true, connected: false }); await flushPromises()
    expect(api.listOpeningInventoryBatches).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
