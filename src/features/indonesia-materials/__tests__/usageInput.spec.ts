import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import UsageInput from '../UsageInput.vue'

describe('per-product usage stepping', () => {
  it('steps an integer by exactly one without inheriting the old minimum offset', async () => {
    const wrapper = mount(UsageInput, { props: { modelValue: '7' } })
    await wrapper.get('[aria-label="增加单件用量1"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['8'])
    await wrapper.get('input').trigger('keydown', { key: 'ArrowDown' })
    expect(wrapper.emitted('update:modelValue')?.[1]).toEqual(['6'])
  })
  it('preserves eight decimal places and permits precise manual typing', async () => {
    const wrapper = mount(UsageInput, { props: { modelValue: '7.12345678' } })
    await wrapper.get('input').trigger('keydown', { key: 'ArrowUp' })
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['8.12345678'])
    await wrapper.get('input').setValue('0.00000001')
    expect(wrapper.emitted('update:modelValue')?.[1]).toEqual(['0.00000001'])
  })
  it('starts an empty row at one and never steps below zero', async () => {
    const wrapper = mount(UsageInput, { props: { modelValue: '' } })
    await wrapper.get('[aria-label="增加单件用量1"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['1'])
    await wrapper.get('[aria-label="减少单件用量1"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[1]).toEqual(['0'])
  })
})
