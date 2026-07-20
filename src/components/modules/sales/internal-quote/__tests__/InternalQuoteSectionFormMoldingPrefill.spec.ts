import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import InternalQuoteSectionForm from '../InternalQuoteSectionForm.vue'

const referenceSnapshot = {
  material_prices: {
    'ABS|750SW': '8.50',
    '1#PP|JM350/K8009': '6.80',
    '1#PP|7032 E3': '6.80',
    '透明PP|5090T': '7.80',
  },
  machine_prices: [{ range: '18A', machine: '180T', shift_price_hkd: '1890' }],
}

function moldingModel(overrides: Record<string, unknown> = {}) {
  return {
    injection_loss_rate_percent: 3,
    injection_lines: [{
      engineering_source_key: 'mold-no:M12#1',
      engineering_synced_fields: ['item', 'mold_no', 'material'],
      item: '挂钩', mold_no: 'M12', material: 'PP', grade: '', color: '', net_weight_g: 0,
      loss_rate_percent: 3, machine_name: '', machine_code: '', cavity: '', sets: 1,
      target_output: 0, cycle_time_seconds: 0, quantity: 1, remark: '', disney_mold_no: '',
      disney_resin_cost_usd_kg: 0, disney_cycle_time_seconds: 0, disney_labor_rate_usd_hr: 0,
      ...overrides,
    }],
    blow_lines: [],
    caixing_tool_plan_rows: [],
  }
}

describe('InternalQuoteSectionForm engineering mold prefill', () => {
  it('locks engineering identity fields but leaves material and machine selection editable', () => {
    const wrapper = mount(InternalQuoteSectionForm, {
      props: {
        code: 'molding',
        modelValue: moldingModel(),
        referenceSnapshot,
        'onUpdate:modelValue': () => undefined,
      },
    })

    const row = wrapper.find('.moldingInjectionTable tbody tr')
    const textarea = row.find('textarea')
    const selects = row.findAll('select')
    const deleteButton = row.find('button.icon')

    expect(wrapper.text()).toContain('已同步 1 项模具')
    expect(textarea.attributes('disabled')).toBeDefined()
    expect(textarea.classes()).toContain('engineering-prefilled')
    expect(row.find('input').attributes('disabled')).toBeDefined()
    expect(selects[0].attributes('disabled')).toBeUndefined()
    expect(selects[1].attributes('disabled')).toBeUndefined()
    expect(selects[1].text()).toContain('7032 E3')
    expect(selects[1].text()).toContain('5090T')
    expect(selects[2].attributes('disabled')).toBeUndefined()
    expect(deleteButton.attributes('disabled')).toBeDefined()
  })

  it('matches and canonicalizes a bare A-code before save while previewing amounts', () => {
    const modelValue = moldingModel({ material: 'ABS', grade: '750SW', net_weight_g: 135, machine_code: '18', sets: 1, target_output: 2800 })
    const wrapper = mount(InternalQuoteSectionForm, {
      props: {
        code: 'molding',
        modelValue,
        referenceSnapshot,
        'onUpdate:modelValue': () => undefined,
      },
    })

    expect(modelValue.injection_lines[0].machine_code).toBe('18A')
    expect(modelValue.injection_lines[0].machine_name).toBe('180T')
    const values = wrapper.findAll('.moldingInjectionTable .snapshot-cell').map((cell) => cell.text())
    expect(values).toEqual(['0.019', '2.603', '0.675', '3.278'])
    expect(wrapper.text()).toContain('注塑实时合计 HKD 3.278')
    expect(wrapper.text()).not.toContain('保存后计算')
  })

  it('canonicalizes a compatible saved grade back to the frozen material pair', () => {
    const modelValue = moldingModel({ material: 'PP', grade: 'JM350/K8009', machine_code: '18' })
    mount(InternalQuoteSectionForm, {
      props: {
        code: 'molding',
        modelValue,
        referenceSnapshot,
        'onUpdate:modelValue': () => undefined,
      },
    })

    expect(modelValue.injection_lines[0].material).toBe('1#PP')
    expect(modelValue.injection_lines[0].grade).toBe('JM350/K8009')
    expect(modelValue.injection_lines[0].machine_code).toBe('18A')
  })

  it('offers fuzzy PP grades and recalculates as soon as a concrete grade is selected', async () => {
    const modelValue = moldingModel({ material: 'PP', grade: '', net_weight_g: 135, machine_code: '18', sets: 1, target_output: 2800 })
    const wrapper = mount(InternalQuoteSectionForm, {
      props: {
        code: 'molding',
        modelValue,
        referenceSnapshot,
        'onUpdate:modelValue': () => undefined,
      },
    })

    const gradeSelect = wrapper.findAll('.moldingInjectionTable select')[1]
    expect(gradeSelect.text()).toContain('JM350/K8009')
    expect(gradeSelect.text()).toContain('7032 E3')
    expect(gradeSelect.text()).toContain('5090T')

    await gradeSelect.setValue(JSON.stringify(['1#PP', '7032 E3']))

    expect(modelValue.injection_lines[0].material).toBe('1#PP')
    expect(modelValue.injection_lines[0].grade).toBe('7032 E3')
    expect(wrapper.findAll('.moldingInjectionTable .snapshot-cell').map((cell) => cell.text())).toEqual(['0.015', '2.083', '0.675', '2.758'])
  })
})
