import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import Picker from '../CartonCustomerPicker.vue'
import type { CartonCustomerResponse } from '@/api/cartonProcurement'
const customers = [
  { id: 'A', customer_code: 'D', customer_name: '迪奇', status: 'ACTIVE' },
  { id: 'B', customer_code: 'OLD', customer_name: '旧客户', status: 'INACTIVE' },
] as CartonCustomerResponse[]
describe('customer selection', () => {
  it('binds a unique complete active name when leaving the field', async () => {
    const wrapper = mount(Picker, { props: { modelValue: '', customers, canCreate: false } })
    await wrapper.get('input').setValue('迪奇')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([''])
    await wrapper.get('input').trigger('focusout')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['D'])
    await wrapper.setProps({ modelValue: 'D' })
    expect(wrapper.text()).not.toContain('请从候选中选择')
    await wrapper.get('input').setValue('迪')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([''])
  })
  it('accepts a unique full normalized customer code on Enter', async () => {
    const wrapper = mount(Picker, { props: { modelValue: '', customers, canCreate: false } })
    await wrapper.get('input').setValue(' ｄ ')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([''])
    await wrapper.get('input').trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['D'])
    await wrapper.setProps({ modelValue: 'D' })
    expect(wrapper.get('input').element.value).toBe('迪奇')
  })
  it('requires a choice for duplicate active names and displays their distinct codes', async () => {
    const rows = [
      { id: 'A', customer_code: 'EDU-A', customer_name: 'EDU', status: 'ACTIVE' },
      { id: 'B', customer_code: 'EDU-B', customer_name: 'EDU', status: 'ACTIVE' },
    ] as CartonCustomerResponse[]
    const wrapper = mount(Picker, { props: { modelValue: '', customers: rows, canCreate: false } })
    await wrapper.get('input').setValue('EDU')
    await wrapper.get('input').trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([''])
    expect(wrapper.get('[aria-label="客户候选"]').text()).toContain('EDU-A')
    expect(wrapper.get('[aria-label="客户候选"]').text()).toContain('EDU-B')
    await wrapper.findAll('button')[1]!.trigger('click')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['EDU-B'])
    await wrapper.setProps({ modelValue: 'EDU-B' })
    await wrapper.get('input').trigger('focusout')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['EDU-B'])
  })
  it('does not bind an inactive customer or create a new customer from text alone', async () => {
    const wrapper = mount(Picker, { props: { modelValue: '', customers, canCreate: true } })
    await wrapper.get('input').setValue('旧客户')
    await wrapper.get('input').trigger('focusout')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([''])
    expect(wrapper.emitted('create')).toBeUndefined()
  })
  it('preserves Chinese composition and binds only after finishing the field', async () => {
    const wrapper = mount(Picker, { props: { modelValue: '', customers, canCreate: false } })
    const input = wrapper.get('input')
    await input.trigger('compositionstart')
    await input.setValue('迪奇')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([''])
    const composingEnter = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true, isComposing: true })
    input.element.dispatchEvent(composingEnter)
    expect(composingEnter.defaultPrevented).toBe(false)
    await input.trigger('compositionend')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([''])
    await input.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['D'])
  })
  it.each([
    { kind: 'code', prefix: 'ED', full: 'EDU', shortName: '客户甲', longName: '客户乙', shortCode: 'ED', longCode: 'EDU' },
    { kind: 'name', prefix: '客户', full: '客户乙', shortName: '客户', longName: '客户乙', shortCode: 'A', longCode: 'B' },
  ])('keeps typing intact when one customer $kind is the prefix of another', async ({ prefix, full, shortName, longName, shortCode, longCode }) => {
    const rows = [
      { id: 'A', customer_code: shortCode, customer_name: shortName, status: 'ACTIVE' },
      { id: 'B', customer_code: longCode, customer_name: longName, status: 'ACTIVE' },
    ] as CartonCustomerResponse[]
    const host = defineComponent({ setup() {
      const value = ref('')
      return () => h(Picker, { modelValue: value.value, 'onUpdate:modelValue': (code: string) => { value.value = code }, customers: rows, canCreate: false })
    } })
    const wrapper = mount(host)
    const input = wrapper.get('input')
    await input.setValue(prefix)
    expect(input.element.value).toBe(prefix)
    expect(wrapper.findComponent(Picker).props('modelValue')).toBe('')
    for (const character of full.slice(prefix.length)) await input.setValue(input.element.value + character)
    expect(input.element.value).toBe(full)
    expect(wrapper.findComponent(Picker).props('modelValue')).toBe('')
    await input.trigger('keydown', { key: 'Enter' })
    expect(wrapper.findComponent(Picker).props('modelValue')).toBe(longCode)
    expect(input.element.value).toBe(longName)
    wrapper.unmount()
  })
  it('uses Enter to confirm the customer without submitting the containing form', async () => {
    const wrapper = mount(Picker, { props: { modelValue: '', customers, canCreate: false } })
    await wrapper.get('input').setValue('迪奇')
    const enter = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true })
    wrapper.get('input').element.dispatchEvent(enter)
    expect(enter.defaultPrevented).toBe(true)
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['D'])
  })
  it('allows choosing a longer matching code while focus moves to its candidate', async () => {
    const rows = [
      { id: 'A', customer_code: 'ED', customer_name: '客户甲', status: 'ACTIVE' },
      { id: 'B', customer_code: 'EDU', customer_name: '客户乙', status: 'ACTIVE' },
    ] as CartonCustomerResponse[]
    const wrapper = mount(Picker, { props: { modelValue: '', customers: rows, canCreate: false } })
    await wrapper.get('input').setValue('ED')
    const candidate = wrapper.get('[aria-label="选择客户 客户乙"]')
    await wrapper.get('input').trigger('focusout', { relatedTarget: candidate.element })
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([''])
    await candidate.trigger('click')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['EDU'])
  })
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
