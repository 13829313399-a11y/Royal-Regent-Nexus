import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import Component from '../CartonReturnDateCorrection.vue'

const source = { movementId: 'M1', documentNo: 'RETURN-1', returnDate: '2026-10-01', postingDate: '2026-10-03', revision: 1, fingerprint: 'date-v1' }
beforeEach(() => { vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-10-20T12:00:00Z')) })
afterEach(() => { vi.useRealTimers() })
it('shows old and new periods, preserves posting/cash facts, and emits the reasoned new date', async () => {
  const wrapper = mount(Component, { props: { source } })
  expect(wrapper.text()).toContain('旧归属月份 2026-10')
  expect(wrapper.text()).toContain('真实回款记录保留')
  await wrapper.get('[aria-label="更正后的实际退货日期"]').setValue('2026-09-30')
  await wrapper.get('[aria-label="实际退货日期更正原因"]').setValue('已核对原退货交接单')
  expect(wrapper.text()).toContain('新归属月份 2026-09')
  await wrapper.get('form').trigger('submit')
  expect(wrapper.emitted('save')).toEqual([[{ return_date: '2026-09-30', reason: '已核对原退货交接单' }]])
  expect(source.postingDate).toBe('2026-10-03')
  wrapper.unmount()
})
it('blocks unchanged/future dates, short reasons and disabled actions, then clears drafts on source revision', async () => {
  const wrapper = mount(Component, { props: { source } })
  await wrapper.get('[aria-label="更正后的实际退货日期"]').setValue('2026-10-01')
  await wrapper.get('[aria-label="实际退货日期更正原因"]').setValue('重新核实依据')
  await wrapper.get('form').trigger('submit')
  expect(wrapper.emitted('save')).toBeUndefined()
  await wrapper.get('[aria-label="更正后的实际退货日期"]').setValue('2026-10-21')
  await wrapper.get('form').trigger('submit')
  expect(wrapper.emitted('save')).toBeUndefined()
  await wrapper.setProps({ source: { ...source, revision: 2, fingerprint: 'date-v2' } })
  expect(wrapper.get<HTMLInputElement>('[aria-label="更正后的实际退货日期"]').element.value).toBe('')
  await wrapper.setProps({ disabled: true })
  await wrapper.get('[aria-label="更正后的实际退货日期"]').setValue('2026-09-30')
  await wrapper.get('form').trigger('submit')
  expect(wrapper.emitted('save')).toBeUndefined()
  wrapper.unmount()
})
