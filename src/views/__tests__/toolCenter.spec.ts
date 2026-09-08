import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ToolCenterView from '@/views/ToolCenterView.vue'
import { navigationGroups } from '@/data/enterpriseMock'


describe('public tool center', () => {
  it('places the shared toolbar between main and cross-factory navigation', () => {
    const labels = navigationGroups.map((group) => group.label)
    expect(labels.indexOf('TOOLS')).toBe(labels.indexOf('MAIN') + 1)
    expect(labels.indexOf('TOOLS')).toBeLessThan(labels.indexOf('CROSS FACTORY'))
    expect(navigationGroups.find((group) => group.label === 'TOOLS')?.items).toContainEqual(
      expect.objectContaining({
        label: '公共工具栏',
        to: '/tools',
        preserveFactory: true,
      }),
    )
  })

  it('keeps the authenticated route and renders only the rebuild placeholder', () => {
    const routerSource = readFileSync(join(process.cwd(), 'src/router/index.ts'), 'utf8')
    expect(routerSource).toMatch(/path: '\/tools',[\s\S]*?requiresAuth: true/)
    expect(routerSource).toContain("component: () => import('@/views/ToolCenterView.vue')")

    const wrapper = mount(ToolCenterView)
    expect(wrapper.get('h1').text()).toBe('公共工具栏')
    expect(wrapper.text()).toContain('模块重构中')
    expect(wrapper.find('input[type="file"]').exists()).toBe(false)
    expect(wrapper.find('[role="tablist"]').exists()).toBe(false)
    expect(wrapper.find('button').exists()).toBe(false)
  })
})
