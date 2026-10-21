import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import Picker from '../WarehouseLocationPicker.vue'

describe('formal warehouse location selection', () => {
  it('lets touch users search and select a formal identity without typing the full label', async () => {
    const wrapper = mount(defineComponent({ components: { Picker }, setup() { return { id: ref(''), disabled: ref(false), places: [
      { id: 'A', label: '一仓／布料A01架', category: 'FABRIC' },
      { id: 'B', label: '一仓／布料B02架', category: 'FABRIC' },
      { id: 'T', label: '一仓／辅料A01架', category: 'ACCESSORY' },
    ] } }, template: '<Picker v-model="id" category="FABRIC" :locations="places" :disabled="disabled" /><output>{{ id }}</output><button class="lock" @click="disabled = true">锁定</button>' }))
    await wrapper.get('input').setValue('Ｂ０２')
    expect(wrapper.findAll('.location-touch-list button').map(row => row.text())).toEqual(['一仓／布料B02架'])
    const details = wrapper.get<HTMLDetailsElement>('details')
    details.element.open = true
    await wrapper.get('.location-touch-list button').trigger('click')
    expect(wrapper.get('output').text()).toBe('B')
    expect(wrapper.get<HTMLInputElement>('input').element.checkValidity()).toBe(true)
    expect(details.element.open).toBe(false)
    await wrapper.get('.lock').trigger('click')
    expect(wrapper.find('details').exists()).toBe(false)
    expect(wrapper.get('input').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
  it('filters by category, requires an explicit position and clears mismatched selections', async () => {
    const wrapper = mount(defineComponent({ components: { Picker }, setup() { return { id: ref(''), category: ref(''), places: [
      { id: 'F', label: '一仓／布料1架', category: 'FABRIC' },
      { id: 'T', label: '一仓／配线1区', category: 'THREAD' },
      { id: 'G', label: '一仓／通用位' },
    ] } }, template: '<select v-model="category"><option value=""></option><option>FABRIC</option><option>THREAD</option></select><Picker v-model="id" :category="category" :locations="places" /><output>{{ id }}</output>' }))
    expect(wrapper.get('input').attributes('disabled')).toBeDefined()
    await wrapper.get('select').setValue('FABRIC')
    expect(wrapper.findAll('datalist option').map(row => row.attributes('value'))).toEqual(['一仓／布料1架'])
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
    expect(wrapper.get('output').text()).toBe('')
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
    expect(wrapper.text()).toContain('先在基础资料建立或分类对应原料分区')
    wrapper.unmount()
  })
})
