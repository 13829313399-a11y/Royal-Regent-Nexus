import { describe, expect, it } from 'vitest'
import { departmentModuleRegistry } from '@/data/enterpriseMock'

describe('carton procurement module entry', () => {
  it('replaces the material planning placeholder with the V2.1 carton procurement structure', () => {
    const modules = departmentModuleRegistry['pmc-warehouse'].modules
    const module = modules.find((item) => item.id === 'carton-procurement')

    expect(module).toBeDefined()
    expect(module).toMatchObject({
      title: '纸箱采购协同',
      owner: '纸箱下单 / 采购 / 仓管',
      status: '核心闭环',
      route: '/modules/pmc-warehouse/carton-procurement',
    })
    expect(module?.statusMetrics).toEqual([
      { label: '订单', value: '人工确认', tone: 'teal' },
      { label: '供应商', value: '固定 1 家', tone: 'blue' },
      { label: '台账', value: '后端持久化', tone: 'green' },
    ])
    expect(module?.children.map((child) => child.label)).toEqual([
      '工作台',
      '纸箱订单',
      '每周核对',
      '交期管理',
      '收料管理',
      '库存管理',
      '月结管理',
      '基础资料',
      '报表中心',
      '系统协同',
    ])
    expect(modules.some((item) => item.id === 'material-plan')).toBe(false)
    expect(modules.some((item) => item.title === '物料计划与齐套')).toBe(false)
  })
})
