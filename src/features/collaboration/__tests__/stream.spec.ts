import { afterEach, expect, it, vi } from 'vitest'
import { consumeStream } from '../stream'
vi.mock('@/lib/http', () => ({ http: { defaults: { baseURL: '/api' } }, dispatchAccessFailure: vi.fn() }))
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })
it('cancels a half-open connection after the idle deadline without leaking timers', async () => {
  vi.useFakeTimers()
  const cancel = vi.fn()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(new ReadableStream({ cancel }), {status:200})))
  const result = consumeStream('start', new AbortController().signal, vi.fn()).catch(error => error)
  await vi.advanceTimersByTimeAsync(35_000)
  expect(String(await result)).toMatch(/stream:(idle|closed)/)
  expect(cancel).toHaveBeenCalledTimes(1)
  expect(vi.getTimerCount()).toBe(0)
})
it('reports an expired cursor from the HTTP handshake as a stream reset', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: { code: 'RESET_REQUIRED' } }), { status: 409 })))
  await expect(consumeStream('expired', new AbortController().signal, vi.fn())).rejects.toThrow('stream:reset')
})
it('decodes split CRLF and multibyte SSE data in order and stops on hydration failure', async () => {
  const a = JSON.stringify({ cursor: 'a', value: '你好' }), b = JSON.stringify({ cursor: 'b' })
  const bytes = new TextEncoder().encode(`: heartbeat\r\n\r\nevent: sync\r\ndata: ${a}\r\n\r\nevent: sync\r\ndata: ${b}\r\n\r\n`)
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(new ReadableStream({ start(controller) { for (const byte of bytes) controller.enqueue(Uint8Array.of(byte)); controller.close() } }), { status: 200 })))
  const applied: string[] = []
  await expect(consumeStream('start', new AbortController().signal, async batch => { if (batch.cursor === 'b') throw Error('hydrate failed'); applied.push(batch.cursor) })).rejects.toThrow('hydrate failed')
  expect(applied).toEqual(['a'])
})
