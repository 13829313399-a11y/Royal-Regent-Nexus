import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { describe, expect, it } from 'vitest'
import DashboardView from '@/views/DashboardView.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import MetricCard from '@/components/dashboard/MetricCard.vue'
import { crossFactoryItems, overviewMetrics } from '@/data/enterpriseMock'
import { useAppStore } from '@/stores/app'

const dashboardCss = readFileSync(
  join(process.cwd(), 'src/components/dashboard/styles/dashboard.css'),
  'utf8',
)

const metricCardSource = readFileSync(
  join(process.cwd(), 'src/components/dashboard/MetricCard.vue'),
  'utf8',
)

function mountDashboard() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useAppStore()
  store.syncAuthenticatedFactoryContext({ userId: 'a', primaryFactoryId: 'huakang-a' })
  const wrapper = mount(DashboardView, { global: { plugins: [pinia] } })
  return { store, wrapper }
}

function activeCards(wrapper: ReturnType<typeof mountDashboard>['wrapper']) {
  return wrapper.findAll('.dashboard-factory-card[data-active="true"]')
}

describe('dashboard jade visual layer', () => {
  it('keeps the jade root namespace, the page container query and a single entrance animation', () => {
    const { wrapper } = mountDashboard()
    const root = wrapper.get('.dashboard-page')
    expect(root.attributes('data-dashboard-ui')).toBe('jade-v2')
    expect(root.classes()).toContain('app-page')
    expect(root.classes()).toContain('space-y-6')
    // 旧的全局级联入场由首页专属规则接管，不与新动画叠加。
    expect(wrapper.find('.reveal-grid').exists()).toBe(false)
    expect(wrapper.get('.dashboard-metrics').exists()).toBe(true)
    expect(dashboardCss).toContain('.dashboard-metric[data-tone=')
    expect(dashboardCss).toContain('@container dashboard-page')
    wrapper.unmount()
  })

  it('keeps the container query on an ancestor so the breakpoint rules can actually match', () => {
    const { wrapper } = mountDashboard()
    const container = wrapper.get('.dashboard-page-container')
    const root = wrapper.get('.dashboard-page')
    // 元素不能查询自己的容器：容器必须落在 .dashboard-page 的祖先节点上。
    expect(container.element.contains(root.element)).toBe(true)
    expect(container.element).not.toBe(root.element)
    expect(root.classes()).not.toContain('dashboard-page-container')
    expect(container.element.parentElement).not.toBeNull()
    wrapper.unmount()
  })

  it('renders one deep-jade hero carrier with decoration kept inside it', () => {
    const { wrapper } = mountDashboard()
    const hero = wrapper.get('.dashboard-hero')
    // 装饰不作为 .space-y-6 的直接兄弟节点插入。
    expect(hero.find('.dashboard-hero__art').exists()).toBe(true)
    expect(hero.find('.dashboard-hero__art').attributes('aria-hidden')).toBe('true')
    expect(hero.find('.dashboard-hero__breath').exists()).toBe(true)
    expect(hero.getComponent(PageHeader).exists()).toBe(true)
    expect(dashboardCss).toContain('--dash-hero-start: #073f38')
    expect(dashboardCss).toContain('--dash-hero-end: #0e5c51')
    expect(dashboardCss).toContain('--dash-champagne: #c5ac7b')
    wrapper.unmount()
  })

  it('presents the unfinished header actions as truly disabled and labels the sample source', () => {
    const { wrapper } = mountDashboard()
    const buttons = wrapper.findAll('.dashboard-hero__actions [data-slot="button"]')
    expect(buttons).toHaveLength(2)
    for (const button of buttons) {
      expect(button.attributes('disabled')).toBeDefined()
      expect(button.attributes('title')).toBeUndefined()
    }
    expect(wrapper.get('.dashboard-hero__note').text()).toBe('示例数据 · 筛选与导出暂未接入')
    wrapper.unmount()
  })

  it('keeps the four metrics, their order and their original string values', () => {
    const { wrapper } = mountDashboard()
    const cards = wrapper.findAllComponents(MetricCard)
    expect(cards).toHaveLength(overviewMetrics.length)
    cards.forEach((card, index) => {
      expect(card.props('metric')).toEqual(overviewMetrics[index])
      expect(card.get('.dashboard-metric__value').text()).toBe(overviewMetrics[index].value)
      expect(card.get('.dashboard-metric__label').text()).toBe(overviewMetrics[index].label)
      expect(card.get('.dashboard-metric__detail').text()).toBe(overviewMetrics[index].detail)
    })
    // 数值保持原始文本，不做从 0 累加的滚动数字。
    expect(metricCardSource).not.toMatch(/parseInt|parseFloat|Number\(|requestAnimationFrame|setInterval/)
    expect(dashboardCss).toContain('font-variant-numeric: tabular-nums')
    wrapper.unmount()
  })

  it('gives each metric a business icon instead of a generic shape', () => {
    const { wrapper } = mountDashboard()
    const iconClasses = wrapper.findAll('[data-metric-icon] svg').map((icon) => icon.classes())
    expect(iconClasses).toHaveLength(4)
    expect(iconClasses[0]).toContain('lucide-clipboard-check-icon')
    expect(iconClasses[1]).toContain('lucide-file-stack-icon')
    expect(iconClasses[2]).toContain('lucide-triangle-alert-icon')
    expect(iconClasses[3]).toContain('lucide-boxes-icon')
    // 不再使用通用几何形状。
    expect(metricCardSource).not.toMatch(/\bCircle\b|\bSquare\b|\bTriangle\b/)
    // 指标卡不是业务入口：没有手型指针和可点击语义。
    expect(wrapper.find('.dashboard-metric.cursor-pointer').exists()).toBe(false)
    expect(wrapper.find('.dashboard-metric[role="button"]').exists()).toBe(false)
    expect(metricCardSource).not.toContain('interactive-surface')
    wrapper.unmount()
  })
})

describe('dashboard factory context behaviour', () => {
  it('keeps the authenticated factory title and follows manual selection including group', async () => {
    const { store, wrapper } = mountDashboard()
    expect(wrapper.getComponent(PageHeader).props('title')).toBe('华康A · 运营总览')
    store.setActiveFactory('huadeng')
    await nextTick()
    expect(wrapper.getComponent(PageHeader).props('title')).toBe('华登 · 运营总览')
    store.setActiveFactory('group')
    await nextTick()
    expect(wrapper.getComponent(PageHeader).props('title')).toBe('集团运营总览')
    wrapper.unmount()
  })

  it('lightly emphasises only the matching factory card and never in group context', async () => {
    const { store, wrapper } = mountDashboard()
    expect(activeCards(wrapper)).toHaveLength(1)
    expect(activeCards(wrapper)[0]!.text()).toContain('华康A')
    expect(activeCards(wrapper)[0]!.text()).toContain('当前厂区')

    store.setActiveFactory('huadeng')
    await nextTick()
    expect(activeCards(wrapper)).toHaveLength(1)
    expect(activeCards(wrapper)[0]!.text()).toContain('华登')

    store.setActiveFactory('group')
    await nextTick()
    expect(activeCards(wrapper)).toHaveLength(0)
    wrapper.unmount()
  })

  it('does not fall back to 华康A or invent entries for a factory without a sample card', async () => {
    const { store, wrapper } = mountDashboard()
    store.setActiveFactory('huakang-c')
    await nextTick()
    expect(activeCards(wrapper)).toHaveLength(0)
    const cards = wrapper.findAll('.dashboard-factory-card')
    expect(cards).toHaveLength(4)
    // 示例数组只有四条记录，不为凑齐 6 张卡而虚构华康C／华康D。
    const cardText = cards.map((card) => card.text()).join(' ')
    expect(cardText).not.toContain('华康C')
    expect(cardText).not.toContain('华康D')
    expect(cardText).not.toContain('当前厂区')
    wrapper.unmount()
  })

  it('keeps long timeline copy on a content-driven connector', () => {
    const { wrapper } = mountDashboard()
    const items = wrapper.findAll('.dashboard-timeline-item')
    expect(items).toHaveLength(crossFactoryItems.length)
    // 语义结构为 ol > li，纯展示事项不做成可点击假按钮。
    expect(wrapper.get('.dashboard-timeline').element.tagName).toBe('OL')
    expect(wrapper.find('.dashboard-timeline button').exists()).toBe(false)
    expect(wrapper.find('.dashboard-timeline [role="button"]').exists()).toBe(false)
    // 最后一条不画连接线，其余条目各自承载随内容增长的连接线。
    expect(items.at(-1)!.find('[data-timeline-rail]').exists()).toBe(true)
    expect(dashboardCss).toContain('.dashboard-timeline-item:not(:last-child) .dashboard-timeline-item__rail::after')
    expect(dashboardCss).toMatch(/top: 16px;\s*bottom: 0;/)
    // 原来的固定 h-12 连接线（48px）已被内容高度驱动取代。
    expect(dashboardCss).not.toMatch(/height: 48px/)
    expect(dashboardCss).not.toMatch(/\bh-12\b/)
  })

  it('keeps the five module rows and shows fixed-width tabular values', () => {
    const { wrapper } = mountDashboard()
    const rows = wrapper.findAll('.dashboard-module-row')
    expect(rows).toHaveLength(5)
    expect(rows[0]!.get('.dashboard-module-row__value').text()).toBe('86')
    expect(dashboardCss).toContain('grid-template-columns: 84px minmax(0, 1fr) 44px;')
    // 模块健康度是示例健康度值，不冒充实测开发完成度。
    expect(rows[0]!.attributes('aria-label')).toContain('示例健康度')
    wrapper.unmount()
  })
})

describe('dashboard motion and style isolation', () => {
  it('enters in one short sequence without reusing the global reveal delays', () => {
    expect(dashboardCss).toContain('animation-delay: calc(var(--metric-index, 0) * 38ms)')
    expect(dashboardCss).toContain('animation: dashboard-metric-in 320ms')
    expect(dashboardCss).toContain('animation: dashboard-panel-in 260ms')
    expect(dashboardCss).toContain('animation: dashboard-hero-breath 3.6s')
    // 页头光感只播放一次，不进入永久循环。
    expect(dashboardCss).toMatch(/animation: dashboard-hero-breath 3\.6s[^;]*1 both;/)
  })

  it('scopes every selector and every token to the dashboard root', () => {
    expect(dashboardCss).not.toMatch(/^\s*:root\b/m)
    expect(dashboardCss).not.toMatch(/^\s*\.dark\b/m)
    expect(dashboardCss).not.toMatch(/:deep\(/)

    // 用括号深度扫描普通规则；跳过 @keyframes / @container / @media 包裹的内容，
    // 也跳过规则体内部的声明块。注释先剥离，避免把说明文字误当成选择器。
    const bareSelectors: string[] = []
    const stack: Array<{ at: boolean; keyframes: boolean }> = []
    const rulesOnly = dashboardCss.replace(/\/\*[\s\S]*?\*\//g, '')
    for (const token of rulesOnly.matchAll(/[^{}]+|[{}]/g)) {
      const text = token[0]!
      if (text === '{') {
        const head = (rulesOnly.slice(0, token.index!).match(/[^{}]*$/) ?? [''])[0]!.trim()
        const parentKeyframes = stack.some((frame) => frame.keyframes)
        stack.push({
          at: head.startsWith('@'),
          keyframes: parentKeyframes || head.startsWith('@keyframes'),
        })
        if (head.length > 0 && !head.startsWith('@') && !parentKeyframes) {
          bareSelectors.push(head.replace(/\s+/g, ' '))
        }
        continue
      }
      if (text === '}') {
        stack.pop()
        continue
      }
      const parent = stack[stack.length - 1]
      if (parent?.at && !parent.keyframes && !/^@(?:media|container|supports)\b/.test(text.trim())) {
        const selector = text.replace(/\s+/g, ' ').trim()
        if (selector.length > 0) {
          bareSelectors.push(selector)
        }
      }
    }

    // 受检规则必须存在，否则边界断言是空的。
    expect(bareSelectors.length).toBeGreaterThan(30)
    for (const selector of bareSelectors) {
      expect(selector).toMatch(/^\.dashboard-page\[data-dashboard-ui='jade-v2'\]/)
    }
    // 主题 token 只定义在首页根节点。
    expect(dashboardCss).toContain(".dashboard-page[data-dashboard-ui='jade-v2'] {\n  --dash-canvas:")
    // 首页装饰层不进入键盘焦点顺序，也不接受指针事件。
    expect(dashboardCss).not.toContain('pointer-events: auto')
  })

  it('reduces the new motion without leaving content transparent', () => {
    expect(dashboardCss).toContain('@media (prefers-reduced-motion: reduce)')
    const reducedMotionBlock = dashboardCss.slice(
      dashboardCss.indexOf('@media (prefers-reduced-motion: reduce)'),
    )
    expect(reducedMotionBlock).toContain('animation: none !important;')
    expect(reducedMotionBlock).toContain('opacity: 1;')
    expect(reducedMotionBlock).toContain('transform: none;')
    expect(reducedMotionBlock).toContain('.dashboard-hero__breath')
  })
})
