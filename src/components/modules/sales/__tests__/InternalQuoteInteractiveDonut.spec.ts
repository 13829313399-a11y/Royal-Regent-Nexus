import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import InternalQuoteInteractiveDonut from '@/components/modules/sales/internal-quote/InternalQuoteInteractiveDonut.vue'

const entries = [
  { key: 'engineering', label: '工程部', amount: 3, color: '#2563eb', detail: '有效计算' },
  { key: 'assembly', label: '装配部', amount: 7, color: '#8b5cf6', detail: '有效计算' },
  { key: 'painting', label: '喷油部', amount: 0, color: '#ef4444', detail: '未参与', inactive: true },
]

describe('InternalQuoteInteractiveDonut', () => {
  it('renders individual high-contrast slices and keeps zero values out of the ring', () => {
    const wrapper = mount(InternalQuoteInteractiveDonut, {
      props: { entries, totalLabel: '部门合计', displayTotal: 10 },
    })

    expect(wrapper.findAll('.donut-slice')).toHaveLength(2)
    expect(wrapper.get('.donut-center').text()).toContain('部门合计')
    expect(wrapper.get('.donut-center').text()).toContain('10.0000')
    expect(wrapper.findAll('.donut-legend-row')).toHaveLength(3)
    expect(wrapper.findAll('.donut-legend-row')[2].classes()).toContain('inactive')
  })

  it('expands a hovered slice and shows its amount and percentage in the center', async () => {
    const wrapper = mount(InternalQuoteInteractiveDonut, {
      props: { entries, totalLabel: '部门合计', displayTotal: 10 },
    })
    const engineeringSlice = wrapper.findAll('.donut-slice')[0]

    await engineeringSlice.trigger('mouseenter')

    expect(engineeringSlice.classes()).toContain('active')
    expect(engineeringSlice.attributes('style')).not.toContain('translate(0, 0)')
    expect(wrapper.get('.donut-center').text()).toContain('工程部')
    expect(wrapper.get('.donut-center').text()).toContain('3.0000')
    expect(wrapper.get('.donut-center').text()).toContain('30.0%')

    await engineeringSlice.trigger('mouseleave')
    expect(wrapper.get('.donut-center').text()).toContain('部门合计')
  })

  it('links legend hover to its slice and supports click-to-pin details', async () => {
    const wrapper = mount(InternalQuoteInteractiveDonut, {
      props: { entries, totalLabel: '部门合计', displayTotal: 10 },
    })
    const assemblyLegend = wrapper.findAll('.donut-legend-row')[1]
    const assemblySlice = wrapper.findAll('.donut-slice')[1]

    await assemblyLegend.trigger('mouseenter')
    expect(assemblySlice.classes()).toContain('active')
    expect(wrapper.get('.donut-center').text()).toContain('装配部')
    expect(wrapper.get('.donut-center').text()).toContain('70.0%')

    await assemblyLegend.trigger('click')
    await assemblyLegend.trigger('mouseleave')
    expect(assemblySlice.classes()).toContain('pinned')
    expect(wrapper.get('.donut-center').text()).toContain('装配部')

    await assemblyLegend.trigger('click')
    expect(wrapper.get('.donut-center').text()).toContain('部门合计')
  })
})
