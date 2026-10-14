import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import Picker from '../WarehouseLocationPicker.vue'

describe('formal warehouse location selection', () => {
  it('filters by category, requires an explicit position and clears mismatched selections', async () => {
    const wrapper = mount(defineComponent({ components: { Picker }, setup() { return { id: ref(''), category: ref(''), places: [
      { id: 'F', label: '一仓／布料1架', category: 'FABRIC' },
      { id: 'T', label: '一仓／配线1区', category: 'THREAD' },
      { id: 'G', label: '一仓／通用位' },
    ] } }, template: '<select v-model="category"><option value=""></option><option>FABRIC</option><option>THREAD</option></select><Picker v-model="id" :category="category" :locations="places" /><output>{{ id }}</output>' }))
    expect(wrapper.get('input').attributes('disabled')).toBeDefined()
    await wrapper.get('select').setValue('FABRIC')
    expect(wrapper.findAll('datalist option').map(row => row.attributes('value'))).toEqual(['一仓／布料1架', '一仓／通用位'])
    expect(wrapper.get('output').text()).toBe('')
    await wrapper.get('input').setValue('一仓／配线1区')
    expect(wrapper.get('output').text()).toBe('')
    await wrapper.get('input').setValue('一仓／布料1架')
    expect(wrapper.get('output').text()).toBe('F')
    await wrapper.get('select').setValue('THREAD')
    expect(wrapper.get('output').text()).toBe('')
    expect(wrapper.get<HTMLInputElement>('input').element.value).toBe('')
    await wrapper.get('input').setValue('一仓／通用位')
    await wrapper.get('select').setValue('FABRIC')
    expect(wrapper.get('output').text()).toBe('G')
    wrapper.unmount()
  })
  it('accepts only a unique active catalog identity and clears it when arbitrary text is typed', async () => {
    const wrapper = mount(defineComponent({ components: { Picker }, setup() { return { id: ref(''), places: [
      { id: 'A', label: '一仓／A01', status: 'ACTIVE' }, { id: 'B', label: '二仓／B01', status: 'INACTIVE' },
    ] } }, template: '<form><Picker v-model="id" :locations="places" /><output>{{ id }}</output></form>' }))
    const input = wrapper.get('input')
    await input.setValue('一仓／A01'); expect(wrapper.get('output').text()).toBe('A')
    expect((input.element as HTMLInputElement).checkValidity()).toBe(true)
    await input.setValue('临时写一个新仓位'); expect(wrapper.get('output').text()).toBe('')
    expect((input.element as HTMLInputElement).checkValidity()).toBe(false)
    await input.setValue('二仓／B01'); expect(wrapper.get('output').text()).toBe('')
    expect(wrapper.findAll('option')).toHaveLength(1)
    wrapper.unmount()
  })
  it('requires setup when no active location is available', () => {
    const wrapper = mount(Picker, { props: { locations: [] } })
    expect(wrapper.get('input').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('先在基础资料建立对应原料分区')
    wrapper.unmount()
  })
})
