import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import InternalQuoteReadiness from '../InternalQuoteReadiness.vue'
import InternalQuotePendingOutput from '../InternalQuotePendingOutput.vue'

describe('quote readiness and first output reporting', () => {
  it('shows actionable department blockers and authoritative counts', () => {
    const wrapper = mount(InternalQuoteReadiness, { props: { readiness: {
      ready_sections: 2, required_sections: 5, state: 'incomplete', blockers: [
        { section_code: 'molding', section_name: '啤机部', state: 'incomplete', reason: '材质未匹配' },
        { section_code: 'assembly', section_name: '装配部', state: 'stale', reason: '上游资料已变更' },
        { section_code: 'painting', section_name: '喷油部', state: 'empty', reason: '尚未填写并保存' },
      ],
    } } })
    expect(wrapper.text()).toContain('2/5 已就绪')
    expect(wrapper.text()).toContain('啤机部：待补齐')
    expect(wrapper.text()).toContain('装配部：待重算')
    expect(wrapper.text()).toContain('喷油部：待填写')
    expect(wrapper.get('progress').attributes('max')).toBe('5')
  })

  it('keeps issued history distinct from current readiness and missing data', async () => {
    const wrapper = mount(InternalQuoteReadiness)
    expect(wrapper.text()).toContain('待读取核价状态')
    expect(wrapper.find('progress').exists()).toBe(false)
    await wrapper.setProps({ readiness: { state: 'issued', ready_sections: 5, required_sections: 5, blockers: [] } })
    expect(wrapper.text()).toContain('已输出 · 保留冻结核价')
    expect(wrapper.find('progress').exists()).toBe(false)
    await wrapper.setProps({ readiness: { state: 'ready', ready_sections: 3, required_sections: 3, blockers: [] } })
    expect(wrapper.text()).toContain('3/3 已就绪')
  })

  it('shows all-time pending count, age, missing timestamps and opens the chosen product', async () => {
    const wrapper = mount(InternalQuotePendingOutput, { props: { pending: {
      count: 15, over_three_days: 8, oldest_hours: 120,
      items: [
        { quote_id: 'root', quote_no: 'HP-001', product_name: '吸尘器', customer: 'Hape', created_at: '2026-10-01', waiting_hours: 120 },
        { quote_id: 'unknown', quote_no: 'OLD', product_name: '历史产品', customer: 'Hape', created_at: '', waiting_hours: null },
      ],
    } } })
    expect(wrapper.text()).toContain('15 个产品')
    expect(wrapper.text()).toContain('超过 3 天 8 个')
    expect(wrapper.text()).toContain('最长等待 5.0 天')
    expect(wrapper.text()).toContain('不受统计周期限制')
    expect(wrapper.text()).toContain('建单时间缺失')
    await wrapper.findAll('button')[0]!.trigger('click')
    expect(wrapper.emitted('open')).toEqual([['root']])
  })

  it('shows an explicit empty pending state', () => {
    const wrapper = mount(InternalQuotePendingOutput, { props: { pending: { count: 0, over_three_days: 0, oldest_hours: null, items: [] } } })
    expect(wrapper.text()).toContain('当前没有待首次输出的产品')
    expect(wrapper.find('button').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('最长等待')
  })
})
