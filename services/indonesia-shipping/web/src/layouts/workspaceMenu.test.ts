import { describe, expect, it } from 'vitest'
import { workspaceMenu } from './workspaceMenu'

describe('workspace menu access boundaries', () => {
  it('keeps all twelve existing business URLs, without introducing group URLs', () => {
    const menu = workspaceMenu(() => true)
    expect(menu.map(group => group.name)).toEqual(['基础资料', '订单与走货'])
    expect(menu.flatMap(group => group.children.map(item => item.path)).sort()).toEqual([
      '/customers', '/products', '/tool-materials', '/supplier-summary', '/quotes', '/dictionaries',
      '/schedules', '/purchase', '/molding-pos', '/material-alerts', '/outbound', '/shipments',
    ].sort())
  })
  it('does not grant sibling pages to a purchase-only account', () => {
    const menu = workspaceMenu(module => module === 'purchase')
    expect(menu.map(group => group.name)).toEqual(['订单与走货'])
    expect(menu[0].children.map(item => item.path)).toEqual(['/purchase', '/material-alerts'])
  })
  it('keeps supplier quotes separately authorized and omits empty groups', () => {
    expect(workspaceMenu(module => module === 'quotes')[0].children).toEqual([
      { key: '/quotes', path: '/quotes', name: '供应商报价' },
    ])
    expect(workspaceMenu(() => false)).toEqual([])
  })
})
