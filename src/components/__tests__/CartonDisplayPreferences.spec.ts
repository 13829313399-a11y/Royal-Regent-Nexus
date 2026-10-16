import { mount } from '@vue/test-utils'
import { afterEach, expect, it } from 'vitest'
import DisplayPreferences from '../CartonDisplayPreferences.vue'
import { moneyPreferenceKey } from '@/features/carton-procurement/moneyPreference'

afterEach(() => window.localStorage.clear())
it('saves personal HKD reference settings explicitly and keeps dimension changes independent', async () => {
  const scope = { userId: 'user', employmentEpoch: 1 }
  const wrapper = mount(DisplayPreferences, { props: { scope, dimensionUnit: 'cm' } })
  try {
    await wrapper.get('[aria-label="我的常用尺寸单位"]').setValue('inch')
    expect(wrapper.emitted('update:dimensionUnit')).toEqual([['inch']])
    expect(window.localStorage.getItem(moneyPreferenceKey(scope))).toBeNull()
    await wrapper.get('[aria-label="我的金额显示币种"]').setValue('HKD')
    await wrapper.get('button').trigger('click')
    expect(wrapper.get('[role="alert"]').text()).toContain('有效汇率')
    await wrapper.get('[aria-label="人民币兑港币参考汇率"]').setValue('1.1')
    await wrapper.get('button').trigger('click')
    expect(wrapper.get('[role="status"]').text()).toContain('已保存')
    expect(JSON.parse(window.localStorage.getItem(moneyPreferenceKey(scope))!)).toEqual({ currency: 'HKD', cnyToHkd: '1.1' })
    await wrapper.setProps({ scope: { userId: 'different', employmentEpoch: 1 } })
    expect(wrapper.get<HTMLSelectElement>('[aria-label="我的金额显示币种"]').element.value).toBe('CNY')
    expect(wrapper.get<HTMLInputElement>('[aria-label="人民币兑港币参考汇率"]').element.value).toBe('')
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
  } finally { wrapper.unmount() }
})
