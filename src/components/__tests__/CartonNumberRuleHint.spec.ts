import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import Hint from '../CartonNumberRuleHint.vue'
import { defaultNumberRule, masterDueRules, type MasterRecord } from '@/api/cartonMaster'

it('shows invalid identifiers next to the field and clears the alert after correction', async () => {
  const wrapper = mount(Hint, { props: { label: '合同号', value: '5156156156161156', rule: { ...defaultNumberRule(), frozen: true, templates: ['SC{9}/{3,4}'] } } })
  expect(wrapper.get('[role="alert"]').text()).toContain('合同号格式不符')
  expect(wrapper.text()).toContain('软提醒')
  await wrapper.setProps({ value: 'SC700146953/200' })
  expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  await wrapper.setProps({ value: 'SC700146953/20000' })
  expect(wrapper.find('[role="alert"]').exists()).toBe(true)
})

it('does not present missing, disabled or another customer rules as a passed format check', async () => {
  const saved = { kind: 'RULE', customer_code: 'DICK', status: 'ACTIVE', data: { item_rule: { ...defaultNumberRule(), user_configured: true, frozen: true, templates: ['{9}'] } } } as MasterRecord
  const wrapper = mount(Hint, { props: { label: '货号', value: '1234567890', rule: masterDueRules([saved], 'DICK').item_rule } })
  expect(wrapper.get('[role="alert"]').text()).toContain('货号格式不符')
  await wrapper.setProps({ rule: masterDueRules([saved], 'OTHER').item_rule })
  expect(wrapper.text()).toContain('不检查货号格式')
  expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  await wrapper.setProps({ rule: { ...saved.data.item_rule!, mode: 'OFF' } })
  expect(wrapper.text()).toContain('不检查货号格式')
  expect(wrapper.find('[role="alert"]').exists()).toBe(false)
})

it('keeps explicit hard rules and legacy prefix checks visible', () => {
  const wrapper = mount(Hint, { props: { label: '合同号', value: 'ABC', rule: { ...defaultNumberRule(), mode: 'BLOCK', prefix: 'SC', min_length: 5 } } })
  expect(wrapper.get('[role="alert"]').text()).toContain('请修改后再保存')
})
