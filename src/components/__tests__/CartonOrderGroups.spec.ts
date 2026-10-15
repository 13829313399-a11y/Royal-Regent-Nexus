import { flushPromises, mount } from '@vue/test-utils'
import { reactive } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Component from '../CartonOrderGroups.vue'
import DimensionInput from '../CartonDimensionInput.vue'
import { groupStorageKey, newOrderGroup, saveGroups, convertOrderGroup } from '@/features/carton-procurement/orderGroups'
import type { CartonCustomerResponse } from '@/api/cartonProcurement'

const mocks = vi.hoisted(() => ({ can: vi.fn(() => true), auth: {} as { currentUser?: { id: string; identity: { employment_epoch: number } }; can?: typeof vi.fn } }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => mocks.auth }))
vi.mock('@/features/carton-procurement/orderGroups', async original => ({ ...await original<typeof import('@/features/carton-procurement/orderGroups')>(), convertOrderGroup: vi.fn() }))
vi.mock('@/lib/http', () => ({ http: {}, getApiErrorMessage: (err: Error) => err.message }))
const customers = [{ id: 'C1', customer_code: 'C', customer_name: '客户' }] as CartonCustomerResponse[]
const props = { factoryId: 'huaxing', customers, defaultUnit: 'inch' }
beforeEach(() => {
  localStorage.clear(); vi.resetAllMocks(); mocks.can.mockReturnValue(true)
  mocks.auth = reactive({ currentUser: { id: 'U', identity: { employment_epoch: 1 } }, can: mocks.can })
})
describe('group draft interaction', () => {
  it('adds PO rows as needed, keeps sources locally and restores them', async () => {
    const w = mount(Component, { props })
    await w.findAll('button').find(button => button.text() === '新增合单草稿组')!.trigger('click')
    expect(w.findAll('[aria-label^="合单 customer_po"]')).toHaveLength(1)
    for (let i = 1; i < 6; i++) await w.findAll('button').find(button => button.text() === '增加 PO / 款式')!.trigger('click')
    expect(w.findAll('[aria-label^="合单 customer_po"]')).toHaveLength(6)
    await w.get('[aria-label="合单 customer_po 1"]').setValue('00012')
    await w.get('[aria-label="合单来源 1"]').setValue('PO.xlsx / 原表第2行')
    await w.get('[aria-label="合单 quantity 1"]').setValue('1000')
    await w.get('[aria-label="合单 required_quantity 1-1"]').setValue('20')
    await w.get('[aria-label="合单 unit_price 1-1"]').setValue('1.25')
    w.unmount()
    const restored = mount(Component, { props })
    expect(restored.findAll('[aria-label^="合单 customer_po"]')).toHaveLength(6)
    expect(restored.get<HTMLInputElement>('[aria-label="合单 customer_po 1"]').element.value).toBe('00012')
    expect(restored.get<HTMLTextAreaElement>('[aria-label="合单来源 1"]').element.value).toContain('原表第2行')
    expect(restored.get<HTMLInputElement>('[aria-label="合单 quantity 1"]').element.value).toBe('1000')
    expect(restored.get<HTMLInputElement>('[aria-label="合单 required_quantity 1-1"]').element.value).toBe('20')
    expect(restored.get<HTMLInputElement>('[aria-label="合单 unit_price 1-1"]').element.value).toBe('1.25')
    await restored.setProps({ factoryId: 'huakang-a' })
    expect(restored.find('[aria-label="合单 customer_po 1"]').exists()).toBe(false)
    restored.unmount()
  })
  it('freezes an uncertain request and replays its exact snapshot without creating a new submission ID', async () => {
    const group = newOrderGroup('inch'); group.rows = [group.rows[0]!]; group.customer_code = 'C'
    Object.assign(group.rows[0]!, { customer_po: 'PO1', contract_no: 'C1', item_no: 'I1', customer_due_date: '2026-11-01' })
    Object.assign(group.rows[0]!.lines[0]!, { packaging_type: '平卡', paper_quality: 'B33', specification: '10*20', required_quantity: '5', unit: '张' })
    saveGroups(localStorage, groupStorageKey('U', 1, 'huaxing'), [group])
    vi.mocked(convertOrderGroup).mockRejectedValueOnce(new Error('网络连接中断')).mockResolvedValueOnce([])
    const w = mount(Component, { props })
    await w.findAll('button').find(button => button.text() === '资料齐全，整组转为待下单订单')!.trigger('click'); await flushPromises()
    expect(w.get('[role="alert"]').text()).toContain('草稿已冻结')
    expect(w.get<HTMLInputElement>('[aria-label="合单 item_no 1"]').element.matches(':disabled')).toBe(true)
    const first = JSON.parse(JSON.stringify(vi.mocked(convertOrderGroup).mock.calls[0]![0]))
    await w.findAll('button').find(button => button.text() === '核对原转单结果 / 重试')!.trigger('click'); await flushPromises()
    expect(vi.mocked(convertOrderGroup).mock.calls[1]![0]).toEqual(first)
    w.unmount()
  })
  it('keeps the form open if browser storage cannot save it', async () => {
    const w = mount(Component, { props })
    await w.findAll('button').find(button => button.text() === '新增合单草稿组')!.trigger('click')
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('存储空间不足') })
    await w.get('[aria-label="合单 customer_po 1"]').setValue('PO-MUST-KEEP')
    await w.findAll('button').find(button => button.text() === '保存并关闭')!.trigger('click')
    expect(w.emitted('close')).toBeUndefined()
    expect(w.get('[role="alert"]').text()).toContain('存储空间不足')
    expect(w.get<HTMLInputElement>('[aria-label="合单 customer_po 1"]').element.value).toBe('PO-MUST-KEEP')
    spy.mockRestore(); w.unmount()
  })
  it('preserves the entered dimensions when changing the declared unit and shows the reference conversion', async () => {
    const w = mount(DimensionInput, { props: { modelValue: 'inch', specification: '10*20', label: '尺寸单位' } })
    expect(w.text()).toContain('25.4 × 50.8 cm / 10 × 20 inch')
    await w.get('select').setValue('cm')
    expect(w.emitted('update:modelValue')).toEqual([['cm']])
    expect(w.props('specification')).toBe('10*20')
    w.unmount()
  })
})
