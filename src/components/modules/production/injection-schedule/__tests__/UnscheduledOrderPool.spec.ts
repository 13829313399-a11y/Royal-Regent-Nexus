import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import UnscheduledOrderPool from '@/components/modules/production/injection-schedule/UnscheduledOrderPool.vue'
import { getInjectionPreviewDataset } from '@/data/injectionScheduleMock'
import type { InjectionOrder } from '@/types/injectionSchedule'

function orderWithDue(
  source: InjectionOrder,
  id: string,
  orderNo: string,
  deliveryDueAt: string,
): InjectionOrder {
  return {
    ...source,
    id,
    orderNo,
    deliveryDueAt,
  }
}

describe('UnscheduledOrderPool', () => {
  it('calculates due labels from the supplied Shanghai business date', () => {
    const dataset = getInjectionPreviewDataset('huaxing')
    const source = dataset.orders[0]!
    const wrapper = mount(UnscheduledOrderPool, {
      props: {
        orders: [
          orderWithDue(source, 'late', 'ORD-LATE', '2026-08-09T23:30:00+08:00'),
          orderWithDue(source, 'today', 'ORD-TODAY', '2026-08-10T00:15:00+08:00'),
          orderWithDue(source, 'future', 'ORD-FUTURE', '2026-08-12T23:59:00+08:00'),
        ],
        molds: dataset.molds,
        planBaseAt: '2026-08-10T08:00:00+08:00',
      },
    })

    expect(wrapper.text()).toContain('已超 1 天')
    expect(wrapper.text()).toContain('今日到期')
    expect(wrapper.text()).toContain('2 天后到期')
  })

  it('does not invent a date when the planning baseline is unavailable', () => {
    const dataset = getInjectionPreviewDataset('huaxing')
    const source = dataset.orders[0]!
    const wrapper = mount(UnscheduledOrderPool, {
      props: {
        orders: [
          orderWithDue(source, 'unknown-base', 'ORD-UNKNOWN', '2026-08-12T08:00:00+08:00'),
        ],
        molds: dataset.molds,
      },
    })

    expect(wrapper.text()).toContain('基准日期缺失')
  })
})
