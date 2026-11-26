import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { normalizeInternalQuotePayload, type EngineeringPayload } from '@/lib/internalQuoteSectionPayload'
import InternalQuoteSectionForm from '../InternalQuoteSectionForm.vue'

const snapshot = { material_prices: { 'ABS|750SW': 7.2 } }
const raw = { materials: [{ item: 'ABS拉管', category: 'auxiliary', auxiliary_category: '其他外购', quantity: 12 }] }
const fx = '[aria-label="胶料加啤工计价公式"]'

function form(payload = normalizeInternalQuotePayload('engineering', raw, snapshot), disabled = false) {
  return mount(InternalQuoteSectionForm, {
    props: { modelValue: payload, code: 'engineering', factoryId: 'huaxing', customer: 'BuzzBee',
      referenceSnapshot: snapshot, rmbHkdRate: .84, disabled },
    global: { stubs: { DialogPortal: { template: '<slot />' } } },
  })
}

describe('华兴 BuzzBee 其他外购', () => {
  it('选择料型后按克重和单条啤工算价，保存重开仍可查看算式', async () => {
    const wrapper = form()
    const columnCount = wrapper.findAll('.engineeringAuxiliary th').length
    await wrapper.get(fx).trigger('click')
    const dialog = wrapper.get('.fx-dialog')
    expect(dialog.get('.confirm').attributes('disabled')).toBeDefined()
    await dialog.get('select').setValue(JSON.stringify(['ABS', '750SW']))
    const [weight, labor] = dialog.findAll('input')
    await weight!.setValue('48')
    await labor!.setValue('0.64')
    expect(dialog.text()).toContain('7.2 ÷ 454 × 48 + 0.64 ÷ 0.84')
    expect(dialog.text()).toContain('18.2777 HKD')
    await dialog.get('.confirm').trigger('click')
    expect(wrapper.findAll('.engineeringAuxiliary th')).toHaveLength(columnCount)
    expect(wrapper.get('.engineeringAuxiliary tbody').text()).toContain('18.278')
    const saved = normalizeInternalQuotePayload('engineering', wrapper.props('modelValue'), snapshot)
    const row = (saved as unknown as EngineeringPayload).materials[0]!
    expect(row.resin_processing_formula).toEqual({ material: 'ABS', grade: '750SW', price_hkd_lb: 7.2, weight_g: 48, labor_rmb: .64 })
    wrapper.unmount()
    const readonly = form(saved, true)
    await readonly.get(fx).trigger('click')
    expect(readonly.get('.fx-result').text()).toContain('1.5231 HKD/条')
    expect(readonly.get('.fx-dialog input').attributes('disabled')).toBeDefined()
    expect(readonly.find('.fx-dialog .confirm').exists()).toBe(false)
    readonly.unmount()
  })

  it('只在目标厂区、客户和类别显示入口，改类别时保留当前单价', async () => {
    const payload = normalizeInternalQuotePayload('engineering', { materials: [{ ...raw.materials[0],
      resin_processing_formula: { material: 'ABS', grade: '750SW', price_hkd_lb: 7.2, weight_g: 48, labor_rmb: 0 } }] }, snapshot)
    const wrapper = form(payload)
    await wrapper.setProps({ factoryId: 'huadeng' })
    expect(wrapper.find(fx).exists()).toBe(false)
    await wrapper.setProps({ factoryId: 'huaxing', customer: '其他' })
    expect(wrapper.find(fx).exists()).toBe(false)
    await wrapper.setProps({ customer: 'BuzzBee' })
    await wrapper.get('[aria-label="辅助材料/外购件类别"]').setValue('吸塑')
    expect(wrapper.find(fx).exists()).toBe(false)
    const row = (wrapper.props('modelValue') as unknown as EngineeringPayload).materials[0]!
    expect(row.resin_processing_formula).toBeUndefined()
    expect(row.unit_price_hkd).toBeCloseTo(7.2 / 454 * 48, 10)
    wrapper.unmount()
  })

  it('取消不覆盖手填价，可以采用零啤工再转回手填', async () => {
    const payload = normalizeInternalQuotePayload('engineering', { materials: [{ ...raw.materials[0],
      unit_price_hkd: 1.25, unit_price_source_currency: 'HKD' }] }, snapshot)
    const wrapper = form(payload)
    const row = (wrapper.props('modelValue') as unknown as EngineeringPayload).materials[0]!
    await wrapper.get(fx).trigger('click')
    await wrapper.get('.fx-dialog select').setValue(JSON.stringify(['ABS', '750SW']))
    await wrapper.get('.fx-dialog input').setValue('32')
    await wrapper.get('.fx-dialog footer button').trigger('click')
    expect(row.resin_processing_formula).toBeUndefined()
    expect(row.unit_price_hkd).toBe(1.25)
    await wrapper.get(fx).trigger('click')
    expect(wrapper.get<HTMLInputElement>('.fx-dialog input').element.value).toBe('')
    await wrapper.get('.fx-dialog select').setValue(JSON.stringify(['ABS', '750SW']))
    const [weight, labor] = wrapper.findAll('.fx-dialog input')
    await weight!.setValue('32')
    await labor!.setValue('0')
    await wrapper.get('.fx-dialog .confirm').trigger('click')
    await wrapper.get(fx).trigger('click')
    await wrapper.get('.fx-dialog footer button').trigger('click')
    expect(row.resin_processing_formula).toBeUndefined()
    expect(row.unit_price_hkd).toBeCloseTo(7.2 / 454 * 32, 10)
    expect(wrapper.get('[aria-label="辅助材料/外购件原单价 HKD"]').attributes('readonly')).toBeUndefined()
    wrapper.unmount()
  })
})
