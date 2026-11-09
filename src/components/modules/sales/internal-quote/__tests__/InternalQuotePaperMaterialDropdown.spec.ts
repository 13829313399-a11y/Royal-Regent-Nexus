import { mount } from '@vue/test-utils'
import { reactive } from 'vue'
import { describe, expect, it } from 'vitest'
import PaperNameSelect from '../InternalQuotePaperNameSelect.vue'
import PaperSelect from '../InternalQuotePaperMaterialSelect.vue'
import PaperEditor from '../InternalQuotePaperPriceEditor.vue'

describe('paper material dropdowns', () => {
  it('shows grouped names without inventing or selecting unconfirmed prices', () => {
    const snapshot = { paper_prices: [{ key: 'confirmed-ab', name: 'A=B', price_factor_hkd: '2.60', remark: '合成测试价' }] }
    const before = JSON.stringify(snapshot)
    const wrapper = mount(PaperSelect, { props: { snapshot, fallback: 2.75 } })
    expect(wrapper.findAll('optgroup').map(g => g.attributes('label'))).toEqual(['单坑（B楞）', '双坑（BC楞）'])
    expect(wrapper.get('option[value="confirmed-ab"]').element.disabled).toBe(false)
    const pending = wrapper.get('option[value="pending:B3B"]')
    expect(pending.element.disabled).toBe(true)
    expect(pending.text()).toContain('待维护价格')
    expect(wrapper.get('select').element.selectedIndex).toBe(0)
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(JSON.stringify(snapshot)).toBe(before)
  })

  it('keeps custom material selections and frozen keys available', async () => {
    const wrapper = mount(PaperSelect, { props: { modelValue: 'old-custom', fallback: 2.75,
      snapshot: { paper_prices: [{ key: 'old-custom', name: '客户专用平卡', price_factor_hkd: '1.95', remark: '' }] } } })
    expect(wrapper.get('select').element.value).toBe('old-custom')
    expect(wrapper.get('optgroup[label="其他已维护材质"]').text()).toContain('客户专用平卡')
    await wrapper.setProps({ disabled: true })
    expect(wrapper.get('select').element.disabled).toBe(true)
  })

  it('chooses a standard name in the price editor without changing its price or key', async () => {
    const rows = reactive([{ key: 'stable-paper', name: '', price_factor_hkd: '3.1500', remark: '保留说明' }])
    const wrapper = mount(PaperEditor, { props: { modelValue: rows } })
    await wrapper.get('select[aria-label="纸材名称"]').setValue('B33+B')
    expect(rows[0]).toEqual({ key: 'stable-paper', name: 'B33+B', price_factor_hkd: '3.1500', remark: '保留说明' })
    await wrapper.setProps({ disabled: true })
    expect(wrapper.findAll('select,input').every(input => input.element.disabled)).toBe(true)
  })

  it('allows custom names and retains existing custom values on opening', async () => {
    const wrapper = mount(PaperNameSelect, { props: { modelValue: '专用纸板' } })
    expect(wrapper.get('select').element.value).toBe('__custom__')
    expect(wrapper.get('input').element.value).toBe('专用纸板')
    await wrapper.get('input').setValue('新专用纸板')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['新专用纸板'])
    await wrapper.setProps({ modelValue: 'A=B' })
    await wrapper.get('select').setValue('__custom__')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([''])
    await wrapper.setProps({ modelValue: '' })
    expect(wrapper.find('input[aria-label="自定义纸材名称"]').exists()).toBe(true)
  })
})
