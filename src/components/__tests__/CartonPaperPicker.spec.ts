import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import Picker from '../CartonPaperPicker.vue'
import Assist from '../CartonMasterOrderAssist.vue'
import { masterPaperOptions, type MasterRecord } from '@/api/cartonMaster'

it('starts blank, opens only on explicit selection or typing, and never auto-selects a match', async () => {
  const wrapper = mount(Picker, { props: { label: '纸质 1', modelValue: '', options: ['A33', 'B3B'] } })
  expect(wrapper.find('[aria-label="纸质 1候选"]').exists()).toBe(false)
  await wrapper.get('button').trigger('click')
  expect(wrapper.text()).toContain('A33')
  await wrapper.get('input').setValue('a3')
  await wrapper.setProps({ modelValue: 'a3' })
  expect(wrapper.text()).not.toContain('B3B')
  expect(wrapper.emitted('update:modelValue')).toEqual([['a3']])
  await wrapper.findAll('button').find(button => button.text() === 'A33')!.trigger('click')
  expect(wrapper.emitted('update:modelValue')!.at(-1)).toEqual(['A33'])
})

it('shows configuration assistance only after matching item/product input', async () => {
  const row = { id: 'A', kind: 'CONFIG', status: 'ACTIVE', code: 'BOX-001', sources: [], data: { product_name: '消防车', lines: [] } } as unknown as MasterRecord
  const wrapper = mount(Assist, { props: { records: [row], customer: '', item: '', contract: '', product: '', lines: [] } })
  expect(wrapper.find('[aria-label="基础资料落单辅助"]').exists()).toBe(false)
  await wrapper.setProps({ item: 'box00' })
  expect(wrapper.text()).toContain('BOX-001')
  await wrapper.setProps({ item: 'NOT-FOUND' })
  expect(wrapper.find('[aria-label="基础资料落单辅助"]').exists()).toBe(false)
})

it('combines only active factory-wide options and historical configurations', () => {
  const records = [
    { kind: 'RULE', customer_code: '', status: 'ACTIVE', data: { paper_types: ['底卡'] } },
    { kind: 'RULE', customer_code: 'customer', status: 'ACTIVE', data: { paper_types: ['客户私有'] } },
    { kind: 'CONFIG', status: 'ACTIVE', data: { lines: [{ packaging_type: '外箱' }] } },
    { kind: 'CONFIG', status: 'INACTIVE', data: { lines: [{ packaging_type: '停用纸品' }] } },
  ] as MasterRecord[]
  expect(masterPaperOptions(records, 'packaging_type')).toEqual(['底卡', '外箱'])
})

it('includes saved pending values and keeps removed history out of suggestions', () => {
  const records = [
    { kind: 'RULE', customer_code: '', status: 'ACTIVE', data: { paper_qualities: ['A35'], hidden_paper_qualities: ['A33'] } },
    { kind: 'CONFIG', status: 'ACTIVE', data: { lines: [{ paper_quality: 'A33' }] } },
  ] as MasterRecord[]
  expect(masterPaperOptions(records, 'paper_quality', { paper_quality: ['A33', 'B3B'] })).toEqual(['A35', 'B3B'])
})

it('keeps independently maintained paper options effective when the shared date rule is inactive', () => {
  const records = [{ kind: 'RULE', customer_code: '', status: 'INACTIVE', data: { paper_types: ['底卡'], hidden_paper_types: ['外箱'] } }] as MasterRecord[]
  expect(masterPaperOptions(records, 'packaging_type', { packaging_type: ['外箱'] })).toEqual(['底卡'])
})
