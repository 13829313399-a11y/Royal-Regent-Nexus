import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import Picker from '../CartonCustomerPicker.vue'
import type { CartonCustomerResponse } from '@/api/cartonProcurement'
const customers = [
  { id: 'A', customer_code: 'D', customer_name: '迪奇', status: 'ACTIVE' },
  { id: 'B', customer_code: 'OLD', customer_name: '旧客户', status: 'INACTIVE' },
] as CartonCustomerResponse[]
describe('customer selection', () => {
  it('starts empty, requires choosing a result, and clears the code when typing again', async () => {
    const wrapper = mount(Picker, { props: { modelValue: '', customers, canCreate: false } })
    expect(wrapper.get('input').element.value).toBe('')
    await wrapper.get('input').setValue('迪')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([''])
    await wrapper.get('[aria-label="选择客户 迪奇"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['D'])
    await wrapper.setProps({ modelValue: 'D' })
    expect(wrapper.get('input').element.value).toBe('迪奇')
    await wrapper.get('input').setValue('另一个')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([''])
    expect(wrapper.text()).toContain('请联系有高级维护权限')
    expect(wrapper.findAll('button')).toHaveLength(0)
  })
  it('requires explicit creation and prevents a duplicate inactive name', async () => {
    const wrapper = mount(Picker, { props: { modelValue: '', customers, canCreate: true } })
    await wrapper.get('input').setValue('新客户')
    expect(wrapper.emitted('create')).toBeUndefined()
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('create')?.[0]).toEqual(['新客户'])
    await wrapper.get('input').setValue('旧客户')
    expect(wrapper.text()).toContain('同名客户已停用')
    expect(wrapper.findAll('button')).toHaveLength(0)
  })
})
