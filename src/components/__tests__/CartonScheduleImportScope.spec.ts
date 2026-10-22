import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import Component from '../CartonScheduleImportScope.vue'
import { emptyScheduleImportScope, scheduleScopeErrors } from '@/api/cartonScheduleCoverage'

beforeEach(() => { vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-10-20T12:00:00Z')) })
afterEach(() => vi.useRealTimers())
it('defaults to incremental with an editable Shanghai business date and hides full coverage fields', async () => {
  vi.setSystemTime(new Date('2026-10-20T16:01:00Z'))
  const scope = emptyScheduleImportScope(), w = mount(Component, { props: { modelValue: scope } })
  expect(scope.scope_mode).toBe('INCREMENTAL'); expect(scope.as_of_date).toBe('2026-10-21')
  expect(w.text()).toContain('不因未出现而推断缺行'); expect(w.text()).toContain('默认当天')
  expect(w.get<HTMLInputElement>('[aria-label="业务排期日期"]').element.value).toBe('2026-10-21')
  expect(w.find('[aria-label="客户交期覆盖开始"]').exists()).toBe(false)
  expect(w.find('[aria-label="客户交期覆盖结束"]').exists()).toBe(false)
  expect(w.find('[aria-label="确认全量排期完整性"]').exists()).toBe(false)
  expect(scheduleScopeErrors(scope)).toEqual([])
  await w.get('[aria-label="业务排期日期"]').setValue('2026-10-19')
  const changed = w.emitted('update:modelValue')!.at(-1)![0] as typeof scope
  expect(changed.as_of_date).toBe('2026-10-19')
  expect(scheduleScopeErrors(changed)).toEqual([])
  expect(scheduleScopeErrors({ ...scope, as_of_date: '' })).toEqual(['请填写完整的业务排期日期。'])
  w.unmount()
})
it('requires explicit full coverage and resets the completeness confirmation when its evidence changes', async () => {
  const scope = { ...emptyScheduleImportScope(), scope_mode: 'FULL' as const, as_of_date: '2026-10-01', coverage_start: '2026-10-01', coverage_end: '2026-10-31', full_scope_confirmed: true }
  const w = mount(Component, { props: { modelValue: scope } })
  expect(scheduleScopeErrors(scope)).toEqual([])
  await w.get('[aria-label="客户交期覆盖结束"]').setValue('2026-11-01')
  const next = w.emitted('update:modelValue')![0]![0] as typeof scope
  expect(next.full_scope_confirmed).toBe(false); expect(next.as_of_date).toBe('2026-10-01')
  await w.setProps({ modelValue: next })
  await w.get('[aria-label="确认全量排期完整性"]').setValue(true)
  expect(w.emitted('update:modelValue')!.at(-1)![0]).toMatchObject({ full_scope_confirmed: true })
  expect(w.text()).toContain('不自动取消采购单')
  await w.setProps({ modelValue: { ...scope, coverage_end: '' } })
  await w.get('[aria-label="排期导入方式"]').setValue('INCREMENTAL')
  const incremental = w.emitted('update:modelValue')!.at(-1)![0] as typeof scope
  expect(incremental).toMatchObject({ scope_mode: 'INCREMENTAL', as_of_date: '2026-10-01', coverage_start: '', coverage_end: '', full_scope_confirmed: false })
  expect(scheduleScopeErrors(incremental)).toEqual([])
  await w.setProps({ modelValue: incremental })
  expect(w.find('[aria-label="客户交期覆盖开始"]').exists()).toBe(false)
  await w.get('[aria-label="排期导入方式"]').setValue('FULL')
  const full = w.emitted('update:modelValue')!.at(-1)![0] as typeof scope
  await w.setProps({ modelValue: full })
  expect(w.find('[aria-label="客户交期覆盖开始"]').exists()).toBe(true)
  expect(scheduleScopeErrors(full)).toHaveLength(2)
  w.unmount()
})
it('validates genuine calendar dates, paired/inclusive ranges and a nonfuture Shanghai version date', () => {
  const scope = { ...emptyScheduleImportScope(), as_of_date: '2026-10-01' }
  expect(scheduleScopeErrors({ ...scope, coverage_start: '2026-10-01' })).toHaveLength(1)
  expect(scheduleScopeErrors({ ...scope, as_of_date: '2026-02-30' })).toHaveLength(1)
  expect(scheduleScopeErrors({ ...scope, as_of_date: '0000-01-01' })).toHaveLength(1)
  expect(scheduleScopeErrors({ ...scope, as_of_date: '2026-10-21' })).toHaveLength(1)
  expect(scheduleScopeErrors({ ...scope, coverage_start: '2026-10-02', coverage_end: '2026-10-01' })).toHaveLength(1)
  expect(scheduleScopeErrors({ ...scope, coverage_start: '2026-10-01', coverage_end: '2026-10-01' })).toEqual([])
  expect(scheduleScopeErrors({ ...scope, scope_mode: 'FULL' })).toHaveLength(2)
})
it('does not alter a frozen import scope', async () => {
  const w = mount(Component, { props: { modelValue: emptyScheduleImportScope(), disabled: true } })
  await w.get('[aria-label="业务排期日期"]').setValue('2026-10-01')
  expect(w.emitted('update:modelValue')).toBeUndefined(); w.unmount()
})
