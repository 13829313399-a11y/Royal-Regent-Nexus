// @vitest-environment jsdom
import { beforeEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { injectionApi } from '@/api/injectionScheduling'
import { useInjectionStore } from '@/stores/injectionScheduling'
import ShiftReports from '../ShiftReports.vue'
import { productionShift } from '../types'

vi.mock('@/api/injectionScheduling', () => ({
  injectionApi: { get: vi.fn() },
}))
it('assigns a post-midnight night shift to its start date using configured boundaries', () => {
  expect(productionShift({}, new Date('2027-01-01T03:00:00+08:00'))).toEqual({
    date: '2026-12-31',
    shift: 'NIGHT',
  })
  expect(
    productionShift(
      { day_start: '06:00', night_start: '18:00' },
      new Date('2026-09-06T18:00:00+08:00'),
    ),
  ).toEqual({ date: '2026-09-06', shift: 'NIGHT' })
  expect(
    productionShift(
      { day_start: '06:00', night_start: '18:00' },
      new Date('2026-09-06T06:00:00+08:00'),
    ),
  ).toEqual({ date: '2026-09-06', shift: 'DAY' })
})
beforeEach(() => {
  setActivePinia(createPinia())
  vi.resetAllMocks()
})
async function setup() {
  const store = useInjectionStore()
  store.factory = 'huaxing'
  vi.mocked(injectionApi.get).mockImplementation(async (path) =>
    path === '/shift-reports'
      ? { rows: [] }
      : {
          runs: [
            {
              id: 'run-1',
              machine_code: '新1',
              mold_code: 'M01',
              status: 'RUNNING',
              actual_start_at: '2026-09-06T08:00:00+08:00',
              physical_shots: 0,
              allocation_mode: 'CO_OUTPUT_UNITS',
              products: [
                { product_code: 'A' },
                { product_code: 'A' },
                { product_code: 'B' },
              ],
            },
          ],
        },
  )
  const mutation = vi
    .spyOn(store, 'mutate')
    .mockResolvedValue({ results: [{ index: 0, ok: true }] })
  const wrapper = mount(ShiftReports, { props: { canReport: true } })
  await flushPromises()
  return {
    store,
    mutation,
    wrapper,
    physical: wrapper.get('input[aria-label="新1累计啤数"]'),
  }
}
it('clears the complete co-output draft on Escape, including hidden good units', async () => {
  const { store, mutation, wrapper, physical } = await setup()
  expect(wrapper.findAll('.inj-product-report')).toHaveLength(2)
  await wrapper.get('.inj-product-report input').setValue('160')
  await physical.trigger('keydown', { key: 'Escape' })
  expect(store.dirty).toBe(false)
  await physical.setValue('80')
  await wrapper
    .findAll('button')
    .find((b) => b.text() === '保存已填报数')!
    .trigger('click')
  expect(mutation).toHaveBeenCalledWith('/shift-reports/bulk', {
    rows: [
      expect.objectContaining({
        physical_shots: 80,
        good_units: {},
        scrap_units: {},
      }),
    ],
  })
  wrapper.unmount()
})
it('reports explicit zero while retaining a blank draft for correction', async () => {
  const { mutation, wrapper, physical } = await setup()
  const save = () =>
    wrapper
      .findAll('button')
      .find((b) => b.text() === '保存已填报数')!
      .trigger('click')
  await physical.setValue('')
  await save()
  expect(mutation).not.toHaveBeenCalled()
  expect(wrapper.text()).toContain('已报零请填写 0')
  await physical.setValue('0')
  await save()
  expect(mutation).toHaveBeenCalledWith('/shift-reports/bulk', {
    rows: [expect.objectContaining({ physical_shots: 0 })],
  })
  wrapper.unmount()
})
