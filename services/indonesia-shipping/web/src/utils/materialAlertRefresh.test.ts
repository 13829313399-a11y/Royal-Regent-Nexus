import { afterEach, expect, it, vi } from 'vitest'
import { MATERIAL_ALERT_REFRESH, watchMaterialAlerts } from './materialAlertRefresh'

afterEach(() => vi.useRealTimers())

it('refreshes immediately after writes/refresh and on focus, including a zero count', async () => {
  vi.useFakeTimers()
  const target = new EventTarget()
  const load = vi.fn().mockResolvedValueOnce(2).mockResolvedValueOnce(1).mockResolvedValue(0)
  const publish = vi.fn()
  const stop = watchMaterialAlerts(load, publish, vi.fn(), target)
  await Promise.resolve()
  target.dispatchEvent(new Event(MATERIAL_ALERT_REFRESH))
  await Promise.resolve()
  target.dispatchEvent(new Event('focus'))
  await Promise.resolve()
  expect(publish.mock.calls.map(([count]) => count)).toEqual([2, 1, 0])
  await vi.advanceTimersByTimeAsync(5 * 60 * 1000)
  expect(load).toHaveBeenCalledTimes(4)
  stop()
  target.dispatchEvent(new Event(MATERIAL_ALERT_REFRESH))
  await vi.advanceTimersByTimeAsync(5 * 60 * 1000)
  expect(load).toHaveBeenCalledTimes(4)
})

it('does not overwrite a newer completion count or a closed workspace with a late response', async () => {
  const target = new EventTarget()
  const requests: ((value: number) => void)[] = []
  const publish = vi.fn()
  const stop = watchMaterialAlerts(() => new Promise<number>(resolve => requests.push(resolve)), publish, vi.fn(), target)
  target.dispatchEvent(new Event(MATERIAL_ALERT_REFRESH))
  requests[1](0); await Promise.resolve()
  requests[0](2); await Promise.resolve()
  expect(publish.mock.calls).toEqual([[0]])
  target.dispatchEvent(new Event(MATERIAL_ALERT_REFRESH))
  stop()
  requests[2](1); await Promise.resolve()
  expect(publish.mock.calls).toEqual([[0]])
})
