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
  expect(stream.closed).toBe(true)
  stream.emit('ping', {})
  expect(live.connected.value).toBe(false)
  Stream.latest.emit('reset', { printers: [], run_version: 'recovered' })
  expect(live.connected.value).toBe(true)
  live.stop()
  expect(stream.closed).toBe(true)
  expect(vi.getTimerCount()).toBe(0)
})

it('reopens on network recovery and focus, and ignores old stream events', () => {
  vi.stubGlobal('EventSource', Stream)
  const receive = vi.fn()
  const live = useThreeDLive(receive)
  live.start()
  const old = Stream.latest
  old.onerror?.()
  window.dispatchEvent(new Event('online'))
  expect(old.closed).toBe(true)
  const recovered = Stream.latest
  recovered.emit('ping', {})
  expect(live.connected.value).toBe(false)
  old.emit('reset', { printers: [], run_version: 'obsolete' })
  expect(receive).not.toHaveBeenCalled()
  recovered.emit('reset', { printers: [], run_version: 'current' })
  expect(live.connected.value).toBe(true)
  recovered.onerror?.()
  window.dispatchEvent(new Event('focus'))
  expect(recovered.closed).toBe(true)
  live.stop()
  const last = Stream.latest
  window.dispatchEvent(new Event('online'))
  expect(Stream.latest).toBe(last)
})

it('revoked access closes the authenticated stream', () => {
  vi.stubGlobal('EventSource', Stream)
  const live = useThreeDLive(vi.fn())
  live.start()
  Stream.latest.emit('access_revoked', { status: 403 })
  expect(Stream.latest.closed).toBe(true)
  expect(live.connected.value).toBe(false)
})
