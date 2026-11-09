import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import PaperSelect from '../InternalQuotePaperMaterialSelect.vue'
import { paperRowsError } from '@/lib/internalQuotePaper'
import PaperEditor from '../InternalQuotePaperPriceEditor.vue'

const papers = [{ key: 'ab', name: 'A=B', price_factor_hkd: '2.60', remark: '已确认测试价' }]
describe('paper controls', () => {
  it('selects a frozen material and allows restoring the legacy factor', async () => {
    const wrapper = mount(PaperSelect, { props: { modelValue: undefined, fallback: 2.75, snapshot: { paper_prices: papers } } })
    await wrapper.get('select').setValue('ab')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['ab'])
    await wrapper.setProps({ modelValue: 'ab' })
    const select = wrapper.get('select')
    select.element.selectedIndex = 0
    await select.trigger('change')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([undefined])
  })
  it('identifies a deleted selection and prevents editing in read-only mode', () => {
    const wrapper = mount(PaperSelect, { props: { modelValue: 'deleted', fallback: 2.75, disabled: true, snapshot: { paper_prices: papers } } })
    expect(wrapper.get('select').element.disabled).toBe(true)
    expect(wrapper.text()).toContain('原纸材已失效')
    expect(wrapper.get('select').element.value).toBe('deleted')
  })
  it('edits catalog prices without changing the stable selection key', async () => {
    const rows = papers.map(p => ({ ...p }))
    const wrapper = mount(PaperEditor, { props: { modelValue: rows } })
    await wrapper.get('input[aria-label="纸材系数 HKD"]').setValue('3.15')
    expect(rows[0]!.price_factor_hkd).toBe('3.15')
    expect(paperRowsError(rows)).toBe('')
    expect(rows[0]!.key).toBe('ab')
    await wrapper.setProps({ disabled: true })
    expect(wrapper.findAll('input').every(i => i.element.disabled)).toBe(true)
  })
})
