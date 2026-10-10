import { http, dispatchAccessFailure } from '@/lib/http'
import type { SyncBatch } from '@/api/collaboration'

export async function consumeStream(cursor: string, signal: AbortSignal, apply: (batch: SyncBatch) => Promise<void>) {
  const url = `${String(http.defaults.baseURL ?? '/api').replace(/\/$/, '')}/collaboration/events?cursor=${encodeURIComponent(cursor)}`
  const response = await fetch(url, { credentials: 'include', signal, headers: { Accept: 'text/event-stream' } })
  if (!response.ok) {
    dispatchAccessFailure(response.status, url)
    const error = await response.json().catch(() => null)
    if (error?.detail?.code === 'RESET_REQUIRED') throw new Error('stream:reset')
    throw new Error(`stream:${response.status}`)
  }
  if (!response.body) throw new Error('stream:empty')
  const reader = response.body.getReader(), decoder = new TextDecoder()
  let buffer = ''
  try {
    while (!signal.aborted) {
      let timeout: ReturnType<typeof setTimeout> | undefined
      const chunk = await Promise.race([
        reader.read(),
        new Promise<never>((_, reject) => { timeout = setTimeout(() => { void reader.cancel(); reject(new Error('stream:idle')) }, 35_000) }),
      ]).finally(() => clearTimeout(timeout))
      if (chunk.done) throw new Error('stream:closed')
      buffer = (buffer + decoder.decode(chunk.value, { stream: true })).replace(/\r\n/g, '\n')
      if (buffer.length > 2_000_000) throw new Error('stream:frame-too-large')
      let boundary: number
      while ((boundary = buffer.indexOf('\n\n')) !== -1) {
        const frame = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2)
        const lines = frame.split('\n'), kind = lines.find(line => line.startsWith('event:'))?.slice(6).trim()
        const data = lines.filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n')
        if (kind === 'session_ended') { dispatchAccessFailure(401, url); throw new Error('stream:401') }
        if (kind === 'reset_required') throw new Error('stream:reset')
        if (kind === 'sync' && data) await apply(JSON.parse(data) as SyncBatch)
      }
    }
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock() }
}
