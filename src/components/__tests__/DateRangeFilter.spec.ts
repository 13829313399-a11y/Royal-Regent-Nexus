import { afterEach, describe, expect, it, vi } from 'vitest'
import { DOMWrapper, flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { parseDate } from '@internationalized/date'
import type { DateRange } from 'reka-ui'
import DateRangeFilter from '../DateRangeFilter.vue'

let wrapper: VueWrapper
const initial = (): DateRange => ({ start: parseDate('2026-10-01'), end: parseDate('2026-10-02') })
async function open() {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  wrapper = mount(DateRangeFilter, { attachTo: document.body, props: {
    label: '业务日期范围', modelValue: initial(),
    'onUpdate:modelValue': (value: DateRange) => { void wrapper.setProps({ modelValue: value }) },
  } })
  await wrapper.get('[aria-label="业务日期范围"]').trigger('click'); await flushPromises()
}
async function clickDay(date: string) {
  const day = new DOMWrapper(document.body).get(`[data-value="${date}"]:not([data-outside-view])`)
  await day.trigger('mouseenter'); await day.trigger('click'); await flushPromises()
}
afterEach(() => { wrapper?.unmount(); document.body.innerHTML = ''; vi.unstubAllGlobals() })

describe('shared carton-style date range', () => {
  it('keeps the applied range after the first click, then applies both dates across months and closes', async () => {
    await open()
    await clickDay('2026-10-29')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(wrapper.get('[aria-label="业务日期范围"]').text()).toContain('2026-10-01 至 2026-10-02')
    expect(new DOMWrapper(document.body).get('[role="status"]').text()).toBe('请选择结束日期')
    await clickDay('2026-11-03')
    expect(wrapper.emitted('update:modelValue')).toHaveLength(1)
    expect(wrapper.get('[aria-label="业务日期范围"]').text()).toContain('2026-10-29 至 2026-11-03')
    expect(document.querySelector('[data-testid="date-range-calendar"]')).toBeNull()
  })
  it('supports selecting one day twice and clearing the whole range', async () => {
    await open()
    await clickDay('2026-10-13'); await clickDay('2026-10-13')
    expect(wrapper.get('[aria-label="业务日期范围"]').text()).toContain('2026-10-13 至 2026-10-13')
    await wrapper.get('[aria-label="业务日期范围"]').trigger('click'); await flushPromises()
    await new DOMWrapper(document.body).findAll('button').find(button => button.text() === '清除日期')!.trigger('click'); await flushPromises()
    expect(wrapper.props('modelValue')).toEqual({ start: undefined, end: undefined })
    expect(wrapper.get('[aria-label="业务日期范围"]').text()).toContain('选择日期范围')
  })
  it('discards an unfinished choice when dismissed and normalizes a backwards range', async () => {
    await open(); await clickDay('2026-10-20')
    await new DOMWrapper(document.body).get('[data-testid="date-range-calendar"]').trigger('keydown', { key: 'Escape' }); await flushPromises()
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    await wrapper.get('[aria-label="业务日期范围"]').trigger('click'); await flushPromises()
    expect(new DOMWrapper(document.body).get('[role="status"]').text()).toBe('请选择开始日期，再选择结束日期')
    await clickDay('2026-10-20'); await clickDay('2026-10-10')
    expect(wrapper.get('[aria-label="业务日期范围"]').text()).toContain('2026-10-10 至 2026-10-20')
  })
})
