import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import InternalQuoteStatusDonut from '@/components/modules/sales/internal-quote/InternalQuoteStatusDonut.vue'

const rows = [
  { key: 'in_progress' as const, label: '进行中', count: 6, percentage: 60, color: '#2563eb' },
  { key: 'completed' as const, label: '已完成', count: 3, percentage: 30, color: '#14b8a6' },
  { key: 'canceled' as const, label: '已取消', count: 1, percentage: 10, color: '#f87171' },
]

describe('InternalQuoteStatusDonut', () => {
  it('renders a scalable vector ring with accessible status segments', () => {
    const wrapper = mount(InternalQuoteStatusDonut, { props: { rows, total: 10, periodLabel: '本月' } })

    expect(wrapper.get('svg').attributes('viewBox')).toBe('0 0 160 160')
    expect(wrapper.findAll('.quote-status-segment')).toHaveLength(3)
    expect(wrapper.get('.quote-status-center').text()).toContain('10')
    expect(wrapper.get('.quote-status-center').text()).toContain('总报价')
    expect(wrapper.get('input[type="range"]').attributes('max')).toBe('3')
  })

  it('previews, locks and slides between status details', async () => {
    const wrapper = mount(InternalQuoteStatusDonut, { props: { rows, total: 10, periodLabel: '本月' } })
    const segments = wrapper.findAll('.quote-status-segment')

    await segments[0]!.trigger('mouseenter')
    expect(wrapper.get('.quote-status-center').text()).toContain('进行中')
    expect(wrapper.get('.quote-status-center').text()).toContain('60.0%')

    await segments[0]!.trigger('click')
    await segments[0]!.trigger('mouseleave')
    expect(wrapper.get('.quote-status-center').text()).toContain('进行中')
    expect(segments[0]!.attributes('aria-pressed')).toBe('true')

    await wrapper.get('input[type="range"]').setValue('2')
    expect(wrapper.get('.quote-status-center').text()).toContain('已完成')
    expect(wrapper.get('.quote-status-center').text()).toContain('3')

    await wrapper.get('button[aria-label="查看下一个报价状态"]').trigger('click')
    expect(wrapper.get('.quote-status-center').text()).toContain('已取消')
  })
})
