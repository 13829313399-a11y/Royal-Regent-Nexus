import { afterEach, expect, it, vi } from 'vitest'
import { useThreeDLive } from '../useThreeDLive'

vi.mock('@/lib/http', () => ({ http: { defaults: { baseURL: '/api' } }, dispatchAccessFailure: vi.fn() }))

class Stream extends EventTarget {
  static latest: Stream
  onerror?: () => void
  closed = false
  constructor(public url: string, public options: unknown) { super(); Stream.latest = this }
  close() { this.closed = true }
  emit(name: string, value: unknown) { this.dispatchEvent(new MessageEvent(name, { data: JSON.stringify(value) })) }
}

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

it('replaces snapshots, degrades on error or silent stall, and closes on unmount', () => {
  vi.useFakeTimers()
  vi.stubGlobal('EventSource', Stream)
  const receive = vi.fn()
  const live = useThreeDLive(receive)
  live.start()
  const stream = Stream.latest
  expect(stream.url).toContain('factory_id=huakang-a')
  expect(stream.options).toEqual({ withCredentials: true })
  stream.emit('reset', { printers: [], run_version: 'first' })
  expect(live.connected.value).toBe(true)
  expect(receive).toHaveBeenCalledTimes(1)
  stream.onerror?.()
  expect(live.connected.value).toBe(false)
  stream.emit('snapshot', { printers: [], run_version: 'second' })
  expect(receive).toHaveBeenCalledTimes(2)
  vi.advanceTimersByTime(20000)
  expect(live.connected.value).toBe(false)
  stream.emit('ping', {})
  expect(live.connected.value).toBe(true)
  live.stop()
  expect(stream.closed).toBe(true)
  expect(vi.getTimerCount()).toBe(0)
})

it('revoked access closes the authenticated stream', () => {
  vi.stubGlobal('EventSource', Stream)
  const live = useThreeDLive(vi.fn())
  live.start()
  Stream.latest.emit('access_revoked', { status: 403 })
  expect(Stream.latest.closed).toBe(true)
  expect(live.connected.value).toBe(false)
})
