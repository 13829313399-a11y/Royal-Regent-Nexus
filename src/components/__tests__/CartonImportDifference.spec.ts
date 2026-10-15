import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import CartonImportDifference from '../CartonImportDifference.vue'

it('compares only differing fields and deduplicates repeated unit errors without hiding other warnings', () => {
  const wrapper = mount(CartonImportDifference, { props: { message: '纸品不一致：尺寸单位（送货单：inch；订单：cm） / 纸质（送货单：B150B；订单：K535A） / 尺寸单位（送货单：inch；订单：cm）；请核对原单' } })
  expect(wrapper.findAll('tbody tr')).toHaveLength(2)
  expect(wrapper.findAll('tbody tr')[0]!.text()).toContain('inchcm')
  expect(wrapper.text()).toContain('请核对原单')
})

it('preserves unrecognized errors verbatim and renders untrusted values as text', () => {
  const wrapper = mount(CartonImportDifference, { props: { message: '找不到订单 <script>bad()</script>' } })
  expect(wrapper.find('table').exists()).toBe(false)
  expect(wrapper.text()).toContain('<script>bad()</script>')
  expect(wrapper.find('script').exists()).toBe(false)
})
