import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// Model the browser's cross-connection transaction scheduler; no shared JS lock
// is provided to the production helper. Readonly transactions would race here.
function storageFactory() {
  const records = new Map<string, string[]>()
  const modes: IDBTransactionMode[] = []
  let queue = Promise.resolve(), abortNext = false, releaseCommit: (() => void) | undefined
  let holdCommit = false
  const factory = {
    open: vi.fn(() => {
      const request = { result: undefined as unknown, onerror: null, onblocked: null, onsuccess: null as (() => void) | null }
      request.result = {
        close: vi.fn(), onversionchange: null,
        transaction(_store: string, mode: IDBTransactionMode) {
          modes.push(mode)
          const transaction = { error: null, oncomplete: null as (() => void) | null, onerror: null, onabort: null as (() => void) | null, objectStore: () => store }
          const reads: { key: string; request: { result?: string[]; onsuccess?: () => void } }[] = []
          const writes = new Map<string, string[]>()
          const store = {
            get(key: string) { const read = { key, request: {} }; reads.push(read); return read.request },
            put(ids: string[], key: string) { writes.set(key, structuredClone(ids)) },
          }
          const run = async () => {
            await Promise.resolve()
            for (const read of reads) { read.request.result = structuredClone(records.get(read.key)); read.request.onsuccess?.() }
            await Promise.resolve()
            if (holdCommit) await new Promise<void>(resolve => { releaseCommit = resolve })
            if (abortNext) { abortNext = false; transaction.onabort?.(); return }
            for (const [key, ids] of writes) records.set(key, ids)
            transaction.oncomplete?.()
          }
          if (mode === 'readwrite') queue = queue.then(run)
          else void run()
          return transaction
        },
      }
      queueMicrotask(() => request.onsuccess?.())
      return request
    }),
  }
  return { factory, records, modes, abort: () => { abortNext = true }, hold: () => { holdCommit = true }, release: () => { holdCommit = false; releaseCommit?.() } }
}

async function loadClaim() { return (await import('../notificationClaims')).claimCollaborationNotification }
beforeEach(() => { vi.resetModules(); vi.stubGlobal('navigator', { locks: undefined }) })
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })

describe('collaboration notification claims without Web Locks', () => {
  it('allows only one of four concurrent windows to claim the same event', async () => {
    const storage = storageFactory(); vi.stubGlobal('indexedDB', storage.factory)
    const claim = await loadClaim()
    const results = await Promise.all(Array.from({ length: 4 }, () => claim('alice:1', 'event-1')))
    expect(results.filter(Boolean)).toHaveLength(1)
    expect(storage.factory.open).toHaveBeenCalledTimes(4)
    expect(storage.modes).toEqual(['readwrite', 'readwrite', 'readwrite', 'readwrite'])
    expect(storage.records.get('alice:1')).toEqual(['event-1'])
  })
  it('waits for commit and never accepts a claim whose transaction aborts', async () => {
    const storage = storageFactory(); storage.hold(); storage.abort(); vi.stubGlobal('indexedDB', storage.factory)
    vi.spyOn(document, 'hasFocus').mockReturnValue(false)
    const claim = await loadClaim(), result = vi.fn()
    const pending = claim('alice:1', 'event-1').then(result)
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(result).not.toHaveBeenCalled()
    storage.release(); await pending
    expect(result).toHaveBeenCalledWith(false)
    expect(storage.records.size).toBe(0)
  })
  it('isolates accounts and employment epochs and retains only 150 event IDs per owner', async () => {
    const storage = storageFactory(); vi.stubGlobal('indexedDB', storage.factory)
    const claim = await loadClaim()
    expect(await claim('alice:1', 'event-1')).toBe(true)
    expect(await claim('alice:2', 'event-1')).toBe(true)
    expect(await claim('bob:1', 'event-1')).toBe(true)
    expect(await claim('alice:1', 'event-1')).toBe(false)
    await Promise.all(Array.from({ length: 150 }, (_, index) => claim('alice:1', `later-${index}`)))
    expect(storage.records.get('alice:1')).toHaveLength(150)
    expect(await claim('alice:1', 'later-149')).toBe(false)
    expect(await claim('alice:1', 'event-1')).toBe(true)
    expect(storage.records.get('alice:1')).toHaveLength(150)
  })
  it('falls back to a visible focused window and deduplicates there when storage is unavailable', async () => {
    vi.stubGlobal('indexedDB', undefined)
    const focus = vi.spyOn(document, 'hasFocus').mockReturnValue(false)
    const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(false)
    const claim = await loadClaim()
    expect(await claim('alice:1', 'event-1')).toBe(false)
    focus.mockReturnValue(true); hidden.mockReturnValue(true)
    expect(await claim('alice:1', 'event-1')).toBe(false)
    hidden.mockReturnValue(false)
    expect(await claim('alice:1', 'event-1')).toBe(true)
    expect(await claim('alice:1', 'event-1')).toBe(false)
    expect(await claim('alice:2', 'event-1')).toBe(true)
  })
  it('keeps the Web Locks path and falls back to IndexedDB when that path fails', async () => {
    const storage = storageFactory(); vi.stubGlobal('indexedDB', storage.factory)
    const request = vi.fn(async (_key: string, action: () => boolean) => action())
    vi.stubGlobal('navigator', { locks: { request } })
    localStorage.removeItem('rr.connect.claims.alice:1')
    const claim = await loadClaim()
    expect(await claim('alice:1', 'event-1')).toBe(true)
    expect(await claim('alice:1', 'event-1')).toBe(false)
    expect(storage.factory.open).not.toHaveBeenCalled()
    request.mockRejectedValueOnce(new Error('Locks unavailable'))
    expect(await claim('alice:1', 'event-2')).toBe(true)
    expect(storage.records.get('alice:1')).toEqual(['event-2'])
  })
  it('bounds an unavailable database open and closes a connection that arrives after the timeout', async () => {
    vi.useFakeTimers()
    vi.spyOn(document, 'hasFocus').mockReturnValue(false)
    const close = vi.fn(), request = { result: { close }, onsuccess: undefined as (() => void) | undefined }
    vi.stubGlobal('indexedDB', { open: () => request })
    const claim = await loadClaim(), pending = claim('alice:1', 'event-1')
    await vi.advanceTimersByTimeAsync(3000)
    expect(await pending).toBe(false)
    request.onsuccess?.()
    expect(close).toHaveBeenCalledTimes(1)
    expect(vi.getTimerCount()).toBe(0)
  })
})
