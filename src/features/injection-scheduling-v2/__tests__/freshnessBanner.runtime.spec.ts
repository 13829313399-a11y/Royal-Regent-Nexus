import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SchedulingFreshnessBanner from '../components/SchedulingFreshnessBanner.vue'

describe('SchedulingFreshnessBanner', () => {
  it('keeps a stale formal snapshot visibly identified and exposes retry', async () => {
    const wrapper = mount(SchedulingFreshnessBanner, {
      props: {
        syncHealth: 'stale',
        sourceMode: 'live',
        sourceMessage: '数据同步暂时中断：网络错误',
        lastSyncedAt: '16:42',
        refreshing: false,
      },
    })

    expect(wrapper.attributes('role')).toBe('status')
    expect(wrapper.text()).toContain('数据已过期')
    expect(wrapper.text()).toContain('当前展示 16:42 的最近正式数据')
    expect(wrapper.text()).toContain('网络错误')

    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })

  it.each([
    ['demo-readonly', 'fallback', '只读演示'],
    ['error', 'live', '正式数据未加载'],
    ['refreshing', 'live', '正在重新同步'],
  ] as const)('renders the %s state explicitly', (syncHealth, sourceMode, expectedText) => {
    const wrapper = mount(SchedulingFreshnessBanner, {
      props: {
        syncHealth,
        sourceMode,
        sourceMessage: 'B1a 模拟状态',
        lastSyncedAt: syncHealth === 'refreshing' ? '16:42' : '',
        refreshing: syncHealth === 'refreshing',
      },
    })

    expect(wrapper.text()).toContain(expectedText)
  })

  it('renders nothing while the formal source is live', () => {
    const wrapper = mount(SchedulingFreshnessBanner, {
      props: {
        syncHealth: 'live',
        sourceMode: 'live',
        sourceMessage: '正式数据库',
        lastSyncedAt: '16:42',
        refreshing: false,
      },
    })

    expect(wrapper.html()).toBe('<!--v-if-->')
  })
})
