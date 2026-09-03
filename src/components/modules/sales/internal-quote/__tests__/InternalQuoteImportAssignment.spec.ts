import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import InternalQuoteImportAssignment from '../InternalQuoteImportAssignment.vue'
import InternalQuoteMappedAssignment from '../InternalQuoteMappedAssignment.vue'
import { normalizeInternalQuotePayload } from '@/lib/internalQuoteSectionPayload'

const components = [{ id: 'main', name: '主体' }, { id: 'phone', name: '电话' }]

describe('one product import with explicit assignments', () => {
  it('starts unassigned, assigns selected rows together and allows explicit skipping', async () => {
    const wrapper = mount(InternalQuoteImportAssignment, { props: {
      modelValue: {}, components,
      rows: [{ key: 'molds:0', label: '外壳', source_row: 2 }, { key: 'molds:1', label: '镜片', source_row: 3 }],
      'onUpdate:modelValue': value => wrapper.setProps({ modelValue: value }),
    } })
    expect((wrapper.get('[aria-label="外壳 应用分项"]').element as HTMLSelectElement).value).toBe('')
    await wrapper.get('[aria-label="勾选 外壳"]').setValue(true)
    await wrapper.get('[aria-label="勾选 镜片"]').setValue(true)
    await wrapper.get('[aria-label="批量应用分项"]').setValue('phone')
    await wrapper.get('button').trigger('click')
    expect(wrapper.props('modelValue')).toEqual({ 'molds:0': 'phone', 'molds:1': 'phone' })
    await wrapper.get('[aria-label="镜片 应用分项"]').setValue('__skip__')
    expect(wrapper.props('modelValue')).toEqual({ 'molds:0': 'phone', 'molds:1': '__skip__' })
    await wrapper.setProps({ disabled: true })
    expect(wrapper.get('[aria-label="外壳 应用分项"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it.each(['engineering', 'painting'] as const)('reassigns %s without dropping source data or changing amount', async (code) => {
    const field = code === 'engineering' ? 'molds' : 'rows'
    const payload = { [field]: [{ item: '外壳', cost_rmb: 9000, import_batch_id: 'batch', pricing_component_id: 'main' }] }
    const wrapper = mount(InternalQuoteMappedAssignment, { props: {
      modelValue: payload, code, components,
      'onUpdate:modelValue': value => wrapper.setProps({ modelValue: value }),
    } })
    await wrapper.get('select').setValue('phone')
    const updated = wrapper.props('modelValue') as Record<string, Array<Record<string, unknown>>>
    expect(updated[field]![0]).toEqual({ ...payload[field]![0], pricing_component_id: 'phone' })
    const normalized = normalizeInternalQuotePayload(code, updated) as Record<string, Array<Record<string, unknown>>>
    expect(normalized[field]![0]!.pricing_component_id).toBe('phone')
    expect(normalized[field]![0]!.import_batch_id).toBe('batch')
    expect(payload[field]![0]!.pricing_component_id).toBe('main')
    wrapper.unmount()
  })
})
