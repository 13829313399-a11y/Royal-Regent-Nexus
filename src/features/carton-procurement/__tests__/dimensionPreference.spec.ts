import { mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { dimensionPreferenceKey, useDimensionPreference, type DimensionPreferenceScope } from '../dimensionPreference'
import DimensionInput from '@/components/CartonDimensionInput.vue'

afterEach(() => { window.localStorage.clear(); vi.restoreAllMocks() })

function harness(initial: DimensionPreferenceScope = { userId: 'alice', employmentEpoch: 1 }) {
  const scope = ref<DimensionPreferenceScope | null>(initial)
  let preference!: ReturnType<typeof useDimensionPreference>
  const wrapper = mount(defineComponent({ setup() { preference = useDimensionPreference(scope); return () => null } }))
  return { wrapper, scope, preference }
}

describe('personal dimension habits', () => {
  it('persists per account and employment identity without carrying another user’s habit across a switch', () => {
    const first = harness()
    first.preference.setUnit('inch')
    first.wrapper.unmount()
    const second = harness()
    try {
      expect(second.preference.unit.value).toBe('inch')
      second.scope.value = { userId: 'bob', employmentEpoch: 1 }
      expect(second.preference.unit.value).toBe('cm')
      second.preference.setUnit('mm')
      second.scope.value = { userId: 'alice', employmentEpoch: 1 }
      expect(second.preference.unit.value).toBe('inch')
      second.scope.value = { userId: 'alice', employmentEpoch: 2 }
      expect(second.preference.unit.value).toBe('cm')
      second.scope.value = null
      second.preference.setUnit('inch')
      expect(second.preference.unit.value).toBe('cm')
    } finally { second.wrapper.unmount() }
  })

  it('handles another tab’s preference update and invalid saved values', () => {
    const { wrapper, preference } = harness()
    try {
      const key = dimensionPreferenceKey({ userId: 'alice', employmentEpoch: 1 })
      window.localStorage.setItem(key, 'mm')
      window.dispatchEvent(new StorageEvent('storage', { key }))
      expect(preference.unit.value).toBe('mm')
      window.localStorage.setItem(key, 'unknown')
      window.dispatchEvent(new StorageEvent('storage', { key }))
      expect(preference.unit.value).toBe('cm')
    } finally { wrapper.unmount() }
  })

  it('reports storage failure while allowing the current session’s choice', () => {
    const { wrapper, preference } = harness()
    try {
      vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota') })
      preference.setUnit('mm')
      expect(preference.unit.value).toBe('mm')
      expect(preference.error.value).toContain('无法保存')
    } finally { wrapper.unmount() }
  })

  it('displays the preferred conversion without editing or relabeling the original unit', async () => {
    const wrapper = mount(DimensionInput, { props: { modelValue: 'inch', specification: '10*20', label: '尺寸显示', readonly: true, preferredUnit: 'mm' } })
    try {
      expect(wrapper.find('select').exists()).toBe(false)
      expect(wrapper.text()).toBe('英寸')
      expect(wrapper.get('span').attributes('title')).toBe('254 × 508 mm（换算参考）')
      await wrapper.setProps({ preferredUnit: 'cm' })
      expect(wrapper.get('span').attributes('title')).toBe('25.4 × 50.8 cm（换算参考）')
      expect(wrapper.emitted('update:modelValue')).toBeUndefined()
      await wrapper.setProps({ modelValue: '' })
      expect(wrapper.text()).toContain('原单位待核实')
      expect(wrapper.text()).not.toContain('25.4 × 50.8')
      await wrapper.setProps({ modelValue: 'cm', specification: '10*20 inch' })
      expect(wrapper.text()).toContain('原规格单位与所选单位不一致，请核对')
    } finally { wrapper.unmount() }
  })

  it('shows an explicitly requested conversion while retaining source units and handling unknown specifications', async () => {
    const wrapper = mount(DimensionInput, { props: { modelValue: 'cm', specification: '25.4*50.8', label: '尺寸显示', readonly: true, showReference: true, preferredUnit: 'inch' } })
    try {
      expect(wrapper.text()).toContain('cm')
      expect(wrapper.text()).toContain('10 × 20 英寸（换算参考）')
      await wrapper.setProps({ preferredUnit: 'mm' })
      expect(wrapper.text()).toContain('254 × 508 mm（换算参考）')
      await wrapper.setProps({ preferredUnit: 'cm' })
      expect(wrapper.text()).toBe('cm')
      await wrapper.setProps({ specification: '2.5*(2+2+2)', preferredUnit: 'inch' })
      expect(wrapper.text()).toBe('cm')
      expect(wrapper.get('span').attributes('title')).toContain('非规则规格按原文保留')
      await wrapper.setProps({ modelValue: '' })
      expect(wrapper.text()).toContain('原单位待核实')
      expect(wrapper.text()).not.toContain('换算参考')
      expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    } finally { wrapper.unmount() }
  })
})
