import { addCalendarHours, addProductionHours } from './calendar'
import { defaultDownstreamBufferHours } from './config'
import type {
  ProductionCalendar,
  ProductionProgress,
  ScheduleTiming,
} from '@/types/injectionScheduling'

export function calculateProductionProgress(
  orderQuantity: number,
  productionReports: number[],
  effectiveDailyTarget: number,
): ProductionProgress {
  const completedQuantity = productionReports.reduce((total, value) => total + value, 0)
  const remainingQuantity = Math.max(orderQuantity - completedQuantity, 0)
  const productionDurationHours = effectiveDailyTarget > 0
    ? remainingQuantity / effectiveDailyTarget * 24
    : Number.POSITIVE_INFINITY
  return {
    orderQuantity,
    completedQuantity,
    remainingQuantity,
    effectiveDailyTarget,
    productionDurationHours,
  }
}

export function calculateScheduleTiming(input: {
  anchorAt: string
  changeoverHours: number
  productionDurationHours: number
  deliveryDueAt: string
  calendar: ProductionCalendar
  downstreamBufferHours?: number
}): ScheduleTiming {
  const plannedStart = addProductionHours(input.anchorAt, input.changeoverHours, input.calendar)
  const plannedEnd = addProductionHours(plannedStart, input.productionDurationHours, input.calendar)
  const inboundAt = addCalendarHours(
    plannedEnd,
    input.downstreamBufferHours ?? defaultDownstreamBufferHours,
  )
  const slackHours = (new Date(input.deliveryDueAt).getTime() - new Date(inboundAt).getTime()) / 3_600_000
  return {
    plannedStart,
    plannedEnd,
    inboundAt,
    deliveryDueAt: input.deliveryDueAt,
    slackHours,
  }
}
