import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import { normalizeInternalQuotePayload, type AssemblyPayload } from '@/lib/internalQuoteSectionPayload'
import InternalQuoteSectionForm from '../InternalQuoteSectionForm.vue'

function assemblyModel() {
  return normalizeInternalQuotePayload('assembly', {
    labor_base_hkd: 260,
    standard_work_hours: 11,
    groups: [
      { name: '成品组装', category: 'assembly', production_qty: 100, teams: 1, processes: [] },
      { name: '成品包装', category: 'packaging', production_qty: 100, teams: 1, processes: [] },
    ],
  }) as AssemblyPayload
}

describe('InternalQuoteSectionForm assembly total people', () => {
  it.each(['组装', '包装'])('%s people controls step by one and reject negative/fractional edits', async label => {
    const modelValue = assemblyModel()
    const groupIndex = label === '组装' ? 0 : 1
    const wrapper = mount(InternalQuoteSectionForm, { props: { code: 'assembly', modelValue } })
    const manual = wrapper.get(`input[aria-label="${label}总人数"]`)
    expect(manual.attributes()).toMatchObject({ min: '0', step: '1' })
    await manual.setValue('-3')
    expect(modelValue.groups[groupIndex].total_persons).toBe(0)
    expect((manual.element as HTMLInputElement).value).toBe('0')
    await manual.setValue('2.9')
    expect(modelValue.groups[groupIndex].total_persons).toBe(2)
    await manual.setValue('')
    expect(modelValue.groups[groupIndex].total_persons).toBeNull()
    const block = wrapper.get(label === '组装' ? '#internal-quote-assembly-assembly-work' : '#internal-quote-assembly-packaging-work')
    await block.findAll('button').find(button => button.text().includes('新增工序'))!.trigger('click')
    const people = wrapper.get(`input[aria-label="${label}工序人数"]`)
    const input = people.element as HTMLInputElement
    expect(people.attributes()).toMatchObject({ min: '0', step: '1' })
    input.stepUp()
    await people.trigger('input')
    expect(modelValue.groups[groupIndex].processes[0].persons).toBe(2)
    input.stepDown()
    await people.trigger('input')
    expect(modelValue.groups[groupIndex].processes[0].persons).toBe(1)
    await people.setValue('-1')
    expect(input.value).toBe('0')
    expect(modelValue.groups[groupIndex].processes[0].persons).toBe(0)
    input.stepDown()
    await people.trigger('input')
    expect(input.value).toBe('0')
    await people.setValue('3.8')
    expect(input.value).toBe('3')
    expect(modelValue.groups[groupIndex].processes[0].persons).toBe(3)
    wrapper.unmount()
  })

  it('switches between a manual total and process-derived total, then restores an empty manual value', async () => {
    const modelValue = assemblyModel()
    const wrapper = mount(InternalQuoteSectionForm, {
      props: {
        code: 'assembly',
        modelValue,
        'onUpdate:modelValue': () => undefined,
      },
    })

    await wrapper.get('input[aria-label="组装总人数"]').setValue('6')
    expect(modelValue.groups[0].total_persons).toBe(6)
    expect(wrapper.get('#internal-quote-assembly-assembly-work').text()).toContain('15.600')

    const assemblySection = wrapper.get('#internal-quote-assembly-assembly-work')
    const addProcess = assemblySection.findAll('button').find((button) => button.text().includes('新增工序'))
    expect(addProcess).toBeDefined()
    await addProcess!.trigger('click')

    expect(modelValue.groups[0].total_persons).toBeNull()
    expect(wrapper.find('input[aria-label="组装总人数"]').exists()).toBe(false)
    expect(wrapper.get('#internal-quote-assembly-assembly-work .assembly-readonly output').text()).toBe('1')

    await wrapper.get('input[aria-label="组装工序人数"]').setValue('3')
    expect(wrapper.get('#internal-quote-assembly-assembly-work .assembly-readonly output').text()).toBe('3')

    await wrapper.get('button[aria-label="删除组装工序"]').trigger('click')
    expect(modelValue.groups[0].processes).toHaveLength(0)
    expect(modelValue.groups[0].total_persons).toBeNull()
    expect(wrapper.get('input[aria-label="组装总人数"]').element).toHaveProperty('value', '')

    await wrapper.get('input[aria-label="包装总人数"]').setValue('4')
    expect(modelValue.groups[1].total_persons).toBe(4)
    expect(wrapper.get('#internal-quote-assembly-packaging-work').text()).toContain('10.400')
  })

  it('explains that JustPlay packaging labor follows the business packaging multiplier', () => {
    const wrapper = mount(InternalQuoteSectionForm, {
      props: {
        code: 'assembly',
        modelValue: assemblyModel(),
        pricingMode: 'component',
        pricingComponents: [{ id: 'component-01', name: '主体', markup_x: 1.15 }],
        activePricingComponentId: 'component-01',
        'onUpdate:modelValue': () => undefined,
      },
    })

    expect(wrapper.get('#internal-quote-assembly-packaging-work').text()).toContain(
      '业务部包装',
    )
    expect(wrapper.get('#internal-quote-assembly-packaging-work').text()).toContain(
      '导出时归入包装明细',
    )
  })
})
