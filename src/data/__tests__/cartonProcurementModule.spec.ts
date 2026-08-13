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

describe('carton mark collaboration module entries', () => {
  it('describes the warehouse Excel-to-PDF check before the unchanged QC PDF-to-photo check', () => {
    const warehouseModule = departmentModuleRegistry['pmc-warehouse'].modules
      .find((item) => item.id === 'carton-mark-check')
    const qcModule = departmentModuleRegistry.qc.modules
      .find((item) => item.id === 'carton-mark-check')

    expect(warehouseModule).toMatchObject({
      title: '箱唛资料模板',
      owner: '纸箱部仓管',
      summary: '客人 PO 箱唛 Excel 与排版 PDF 核对，确认文字不变后流转 QC 实拍核验',
      stats: 'Excel → PDF → QC',
    })
    expect(warehouseModule?.statusMetrics).toEqual([
      { label: '客人原稿', value: 'Excel', tone: 'teal' },
      { label: '印刷箱唛', value: 'PDF', tone: 'blue' },
      { label: '流转', value: 'QC', tone: 'amber' },
    ])
    expect(warehouseModule?.children.map((child) => child.label)).toEqual([
      '客人 Excel',
      '印刷 PDF',
      '内容核对',
      'QC 流转',
    ])

    expect(qcModule).toMatchObject({
      title: '箱唛核验',
      owner: 'QC / 纸箱部协同',
      summary: '承接纸箱部已核对的打印 PDF，使用现场箱唛照片逐项核验文字内容',
      stats: '打印 PDF · 现场照片',
      route: '/modules/qc/carton-mark-check',
    })
    expect(qcModule?.statusMetrics).toEqual([
      { label: '基准', value: 'PDF', tone: 'blue' },
      { label: '现场', value: '照片', tone: 'teal' },
      { label: '比对', value: '逐项', tone: 'amber' },
    ])
    expect(departmentModuleRegistry.qa.modules.some((item) => item.id === 'carton-mark-check')).toBe(false)
  })
})
