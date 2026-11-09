import { afterEach, describe, expect, it } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import View from './BomMaterialMatching.vue'
import { newNode, type Material } from './api'

let wrapper: VueWrapper
const materials: Material[] = [{ id: 'm1', code: '04-01-00001', name: '裁片', version: 2, status: 'ACTIVE',
  data: { unit: '套', engineering: { group: '04-01', department: '裁床', attribute: '自制', approval: 'APPROVED' } } }]
const nodes = () => ['自制', '委外'].map((attribute, index) => ({ ...newNode(), key: `n${index}`, source_code: '04-01-00001',
  source_name: '裁片', unit: '套', source: { '物料属性': attribute } }))
const start = () => { wrapper = mount(View, { props: { nodes: nodes(), materials } }) }
afterEach(() => wrapper?.unmount())

describe('unmatched material review panel', () => {
  it('requires per-row opt-in and exposes conflicting attributes without a selectable candidate', async () => {
    start(); await wrapper.get('button').trigger('click')
    const boxes = wrapper.findAll('input[type=checkbox]')
    expect(boxes[0]!.element).toHaveProperty('checked', false)
    expect(boxes[1]!.attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('来源属性与档案不同')
    expect(wrapper.findAll('button')[1]!.attributes('disabled')).toBeDefined()
    await boxes[0]!.setValue(true); await wrapper.findAll('button')[1]!.trigger('click')
    expect(wrapper.emitted('apply')).toEqual([[[{ row: 1, key: 'n0', material_id: 'm1', material_version: 2 }]]])
  })
  it('clears the preview and selection when nodes or material versions change', async () => {
    start(); await wrapper.get('button').trigger('click'); await wrapper.findAll('input')[0]!.setValue(true)
    await wrapper.setProps({ materials: [{ ...materials[0]!, version: 3 }] })
    expect(wrapper.findAll('input')).toHaveLength(0)
    await wrapper.get('button').trigger('click'); expect(wrapper.findAll('input')[0]!.element).toHaveProperty('checked', false)
    await wrapper.setProps({ nodes: nodes().map(n => ({ ...n, process: '新工序' })) })
    expect(wrapper.findAll('input')).toHaveLength(0)
  })
  it('clears choices and blocks application on write permission loss', async () => {
    start(); await wrapper.get('button').trigger('click'); await wrapper.findAll('input')[0]!.setValue(true)
    await wrapper.setProps({ disabled: true })
    expect(wrapper.findAll('input')).toHaveLength(0); expect(wrapper.get('button').attributes('disabled')).toBeDefined()
    expect(wrapper.emitted('apply')).toBeUndefined()
  })
})
