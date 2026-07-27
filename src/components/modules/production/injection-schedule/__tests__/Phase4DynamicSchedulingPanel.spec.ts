import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import Phase4DynamicSchedulingPanel from '@/components/modules/production/injection-schedule/Phase4DynamicSchedulingPanel.vue'

function props(overrides: Record<string, unknown> = {}) {
  return {
    version: {
      id: 'draft-18',
      versionNo: 18,
      revision: 7,
      status: 'draft' as const,
      businessDate: '2026-07-25',
    },
    orders: [{
      id: 'order-1',
      orderNo: 'HX-001',
      productName: '底座',
      outstandingQty: 600,
      producedQty: 400,
      revision: 4,
      priorityCode: 'P0' as const,
      priorityFlag: 'P0',
      estimatedFinishAt: '2026-07-26T16:00:00+08:00',
    }],
    machines: [{
      id: 'machine-23',
      machineCode: 'New23',
      machineName: '新23号机',
      status: 'available',
    }],
    tasks: [{
      id: 'task-1',
      orderId: 'order-1',
      orderNo: 'HX-001',
      productName: '底座',
      machineId: 'machine-23',
      machineCode: 'New23',
      plannedQty: 600,
      plannedFinishAt: '2026-07-26T16:00:00+08:00',
      locked: false,
      protected: false,
      executionStatus: 'running',
    }],
    actuals: [{
      id: 'actual-1',
      orderId: 'order-1',
      orderNo: 'HX-001',
      machineCode: 'New23',
      shiftDate: '2026-07-25',
      shiftCode: 'day' as const,
      source: 'manual' as const,
      legacyShiftCode: 'A' as const,
      actualQty: 120,
      cumulativeProducedQty: 520,
      outstandingQty: 480,
      estimatedFinishAt: '2026-07-26T20:00:00+08:00',
      createdByName: '计划员',
      createdAt: '2026-07-25T20:10:00+08:00',
      reason: '',
      revision: 2,
      correctionCount: 1,
      correctedByName: '主管',
      correctedAt: '2026-07-25T20:20:00+08:00',
      canCorrect: true,
    }],
    lastRun: {
      id: 'run-1',
      runType: 'local_replan' as const,
      status: 'applied' as const,
      triggerType: 'machine_downtime',
      reason: 'New23 临时停机',
      affectedMachineCount: 2,
      affectedTaskCount: 3,
      movedTaskCount: 2,
      createdAt: '2026-07-25T08:00:00+08:00',
      createdByName: '计划员',
      explanations: ['服务端考虑 12 单，PASS 自动排入 8 单'],
    },
    impacts: [{
      id: 'task-1',
      orderNo: 'HX-001',
      machineCode: 'New23',
      beforeFinishAt: '2026-07-26T16:00:00+08:00',
      afterFinishAt: '2026-07-26T20:00:00+08:00',
      etaShiftMinutes: 240,
      deliverySlackBeforeHours: 16,
      deliverySlackAfterHours: 12,
      shortageQty: 480,
    }],
    skipped: [{
      id: 'conflict-1',
      label: 'HX-002',
      status: 'unknown' as const,
      reason: '缺少模具尺寸',
    }],
    barriers: [{
      id: 'task-1',
      label: 'New23 · HX-001',
      reason: '生产中，自动草稿和局部重排不会移动',
    }],
    lastActualReplay: false,
    canAutomate: true,
    canWriteActuals: true,
    busy: false,
    actualsLoading: false,
    error: '',
    ...overrides,
  }
}

describe('Phase4DynamicSchedulingPanel', () => {
  it('renders PASS-only automation, protected barriers, ETA impact, and controlled A/B actuals', () => {
    const wrapper = mount(Phase4DynamicSchedulingPanel, { props: props() })

    expect(wrapper.text()).toContain('只有硬约束 PASS 会以 source=auto 写入草稿')
    expect(wrapper.text()).toContain('UNKNOWN · HX-002')
    expect(wrapper.text()).toContain('New23 · HX-001')
    expect(wrapper.text()).toContain('ETA +240 分钟')
    expect(wrapper.text()).toContain('白班（A）')
    expect(wrapper.text()).toContain('夜班（B）')
    expect(wrapper.text()).toContain('不代表 IoT 自动采集')
    expect(wrapper.text()).toContain('已更正 1 次')
    expect(wrapper.text()).toContain('不自动发布')
  })

  it('emits an automatic draft request only after an audited reason is entered', async () => {
    const wrapper = mount(Phase4DynamicSchedulingPanel, { props: props() })
    const generate = wrapper.findAll('button').find(
      (button) => button.text().includes('预览自动排程影响'),
    )
    expect(generate).toBeTruthy()

    await generate!.trigger('click')
    expect(wrapper.text()).toContain('自动排程原因至少填写 4 个字符')
    expect(wrapper.emitted('generate-auto-draft')).toBeUndefined()

    await wrapper.find('textarea[placeholder*="生成本周自动排程草稿"]').setValue(
      '按当前交期生成自动草稿',
    )
    await generate!.trigger('click')

    expect(wrapper.emitted('generate-auto-draft')).toEqual([[
      {
        reason: '按当前交期生成自动草稿',
        horizonEndAt: '',
      },
    ]])
  })

  it('enters audited correction mode from an existing actual and disables all writes when read-only', async () => {
    const wrapper = mount(Phase4DynamicSchedulingPanel, { props: props() })
    const correct = wrapper.findAll('button').find((button) => button.text() === '更正')
    await correct!.trigger('click')
    expect(wrapper.text()).toContain('提交审计更正')
    expect(wrapper.text()).toContain('更正原因')

    await wrapper.setProps({ canAutomate: false, canWriteActuals: false })
    const writeButtons = wrapper.findAll('button').filter((button) => (
      button.text().includes('预览自动排程影响')
      || button.text().includes('预览局部重排影响')
      || button.text().includes('提交审计更正')
    ))
    expect(writeButtons.every((button) => button.attributes('disabled') !== undefined)).toBe(true)
  })

  it('caps large order, task, and actual collections instead of rendering 1500 rows at once', () => {
    const base = props()
    const orders = Array.from({ length: 1_500 }, (_, index) => ({
      ...base.orders[0],
      id: `order-${index}`,
      orderNo: `HX-${String(index).padStart(4, '0')}`,
    }))
    const tasks = Array.from({ length: 1_500 }, (_, index) => ({
      ...base.tasks[0],
      id: `task-${index}`,
      orderId: `order-${index}`,
      orderNo: `HX-${String(index).padStart(4, '0')}`,
    }))
    const actuals = Array.from({ length: 1_500 }, (_, index) => ({
      ...base.actuals[0],
      id: `actual-${index}`,
      orderId: `order-${index}`,
      orderNo: `HX-${String(index).padStart(4, '0')}`,
    }))
    const wrapper = mount(Phase4DynamicSchedulingPanel, {
      props: props({ orders, tasks, actuals }),
    })
    const selects = wrapper.findAll('select')

    expect(selects[0].findAll('option')).toHaveLength(120)
    expect(selects[1].findAll('option')).toHaveLength(160)
    expect(wrapper.findAll('tbody tr')).toHaveLength(200)
    expect(wrapper.text()).toContain('当前仅渲染最近 200 条')
  })

  it('sorts and displays all formal P0-P3 codes without interpreting the raw priority flag', () => {
    const base = props()
    const orders = [
      {
        ...base.orders[0],
        id: 'order-p3',
        orderNo: 'HX-P3',
        priorityCode: 'P3' as const,
        priorityFlag: 'P0 特急（旧原始文字）',
        outstandingQty: 900,
      },
      {
        ...base.orders[0],
        id: 'order-p2',
        orderNo: 'HX-P2',
        priorityCode: 'P2' as const,
        priorityFlag: '无法识别的原始值',
        outstandingQty: 800,
      },
      {
        ...base.orders[0],
        id: 'order-p1',
        orderNo: 'HX-P1',
        priorityCode: 'P1' as const,
        priorityFlag: '',
        outstandingQty: 700,
      },
      {
        ...base.orders[0],
        id: 'order-p0',
        orderNo: 'HX-P0',
        priorityCode: 'P0' as const,
        priorityFlag: '普通',
        outstandingQty: 600,
      },
    ]
    const wrapper = mount(Phase4DynamicSchedulingPanel, {
      props: props({ orders }),
    })
    const labels = wrapper.findAll('select')[0]
      .findAll('option')
      .map((option) => option.text())

    expect(labels).toEqual([
      'P0 · HX-P0 · 欠 600',
      'P1 · HX-P1 · 欠 700',
      'P2 · HX-P2 · 欠 800',
      'P3 · HX-P3 · 欠 900',
    ])
    expect(wrapper.text()).not.toContain('P0 特急（旧原始文字）')
    expect(wrapper.text()).not.toContain('无法识别的原始值')
  })
})
