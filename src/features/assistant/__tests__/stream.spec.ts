import { describe, expect, it } from 'vitest'
import { parseSSE } from '../stream'
import { assistantUrl } from '../api'

function bytes(values: Uint8Array[]) { return new ReadableStream<Uint8Array>({ start(c) { values.forEach(v => c.enqueue(v)); c.close() } }) }
describe('SSE framing', () => {
  it('preserves Chinese split at every UTF-8 byte; CRLF, comments and multiline data', async () => {
    const raw = new TextEncoder().encode(': heartbeat\r\nevent: response.delta\r\ndata: 曜\r\ndata: 灵\r\n\r\nevent: run.completed\ndata: {}\n\n')
    const result = []
    for await (const item of parseSSE(bytes([...raw].map(b => new Uint8Array([b]))))) result.push(item)
    expect(result).toEqual([{ event: 'response.delta', data: '曜\n灵' }, { event: 'run.completed', data: '{}' }])
  })
  it('rejects an unterminated event instead of claiming success', async () => {
    await expect((async () => { for await (const _ of parseSSE(bytes([new TextEncoder().encode('data: partial')]))) { /* consume */ } })()).rejects.toThrow('中断')
  })
  it('uses the existing API base without duplicate api', () => {
    expect(assistantUrl('/sessions','/api/')).toBe('/api/assistant/sessions')
    expect(assistantUrl('/sessions','https://example.test/api')).toBe('https://example.test/api/assistant/sessions')
  })
})
