import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { describe, expect, it } from 'vitest'
import MachineMasterEditor from '@/components/modules/production/injection-schedule/MachineMasterEditor.vue'
import type { InjectionMachineRecord } from '@/types/injectionSchedule'

const timestamp = '2026-07-23T08:00:00+08:00'

function machine(): InjectionMachineRecord {
  return {
    id: 'machine-1',
    factoryId: 'huaxing',
    machineCode: '旧1',
    machineName: '旧1号机',
    workshop: 'old',
    machineClass: '7A',
    tonnageT: 120,
    processType: '注塑',
    robotType: '双臂',
    fixtureType: '',
    maxShotWeightG: 500,
    tieBarXMm: 450,
    tieBarYMm: 420,
    moldThicknessMinMm: 180,
    moldThicknessMaxMm: 420,
    openingStrokeMm: 520,
    ejectorStrokeMm: 160,
    status: 'available',
    availableAt: timestamp,
    capabilities: [],
    materialRules: ['ABS', 'PC'],
    qualityStatus: 'ready',
    provenance: {},
    sourceBatchId: 'batch-1',
    revision: 3,
    createdBy: 'planner-1',
    createdAt: timestamp,
    updatedBy: 'planner-1',
    updatedAt: timestamp,
  }
}

describe('MachineMasterEditor', () => {
  it('round-trips material restrictions and keeps Chinese robot labels', async () => {
    const wrapper = mount(MachineMasterEditor, {
      props: {
        open: true,
        factoryName: '华兴厂区',
        machine: machine(),
      },
      global: {
        stubs: { Teleport: true },
      },
    })
    await nextTick()

    const materialLabel = wrapper.findAll('label').find(
      (label) => label.text().includes('材料限制'),
    )!
    const materialInput = materialLabel.find<HTMLInputElement>(
      'input:not([type="checkbox"])',
    )
    expect(materialInput.element.value).toBe('ABS、PC')
    await materialInput.setValue('ABS、PC、PP')
    await wrapper.find('form').trigger('submit')

    const payload = wrapper.emitted('save')?.[0]?.[0] as {
      machineId: string
      expectedRevision: number
      input: Record<string, unknown>
    }
    expect(payload.machineId).toBe('machine-1')
    expect(payload.expectedRevision).toBe(3)
    expect(payload.input).toMatchObject({
      machineCode: '旧1',
      robotType: '双臂',
      materialRules: ['ABS', 'PC', 'PP'],
    })
    expect(payload.input.materialRules).not.toContain('screw:')
    expect(wrapper.find('input[placeholder="例如：旧2"]').attributes('disabled')).toBeDefined()
  })
})
