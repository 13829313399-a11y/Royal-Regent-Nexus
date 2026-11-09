import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mock = vi.hoisted(() => ({ instances: [], analyze: vi.fn() }))
vi.mock('../src/lib/codexImport.js', () => ({ analyzeCodexFile: mock.analyze }))
vi.mock('../src/lib/codexParse.worker.js?worker&inline', () => ({
  default: class {
    constructor() {
      this.sent = []
      this.terminate = vi.fn()
      mock.instances.push(this)
    }
    postMessage(...args) { this.sent.push(args) }
  },
}))

import { cancelCodexParsing, parseCodexOffThread } from '../src/lib/codexOffThread.js'

beforeEach(() => {
  mock.instances.length = 0
  mock.analyze.mockReset()
  vi.stubGlobal('Worker', function Worker() {})
})
afterEach(() => {
  cancelCodexParsing()
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('codex background parsing', () => {
  it('retains the source buffer and delivers the matching worker result', async () => {
    const buffer = new Uint8Array([1, 2, 3]).buffer
    const result = parseCodexOffThread('来源.xlsx', buffer, 'hdd')
    const worker = mock.instances[0]
    const [message] = worker.sent[0]
    expect(worker.sent[0]).toHaveLength(1)
    expect(message).toMatchObject({ fileName: '来源.xlsx', buffer, kind: 'hdd' })
    worker.onmessage({ data: { id: message.id, ok: true, result: { kind: 'hdd', rows: [42] } } })
    await expect(result).resolves.toEqual({ kind: 'hdd', rows: [42] })
    expect([...new Uint8Array(buffer)]).toEqual([1, 2, 3])
  })

  it('cancels every pending request and creates a fresh worker on retry', async () => {
    const first = parseCodexOffThread('一.xlsx', new ArrayBuffer(1)).catch((error) => error)
    const second = parseCodexOffThread('二.xlsx', new ArrayBuffer(1)).catch((error) => error)
    const oldWorker = mock.instances[0]
    cancelCodexParsing()
    expect((await first).name).toBe('AbortError')
    expect((await second).name).toBe('AbortError')
    expect(oldWorker.terminate).toHaveBeenCalledOnce()
    const retry = parseCodexOffThread('三.xlsx', new ArrayBuffer(1))
    const newWorker = mock.instances[1]
    expect(newWorker).not.toBe(oldWorker)
    newWorker.onmessage({ data: { id: newWorker.sent[0][0].id, ok: true, result: '重新解析成功' } })
    await expect(retry).resolves.toBe('重新解析成功')
  })

  it('rejects all waiting requests if a worker fails, allowing a fresh retry', async () => {
    const result = parseCodexOffThread('损坏.xlsx', new ArrayBuffer(1)).catch((error) => error)
    mock.instances[0].onerror()
    expect((await result).message).toMatch(/后台解析失败/)
    expect(mock.instances[0].terminate).toHaveBeenCalledOnce()
  })

  it('uses the same parser without Worker support', async () => {
    vi.stubGlobal('Worker', undefined)
    mock.analyze.mockResolvedValue({ invoices: [1] })
    const buffer = new ArrayBuffer(2)
    await expect(parseCodexOffThread('来源.xlsx', buffer, 'hxg')).resolves.toEqual({ invoices: [1] })
    expect(mock.analyze).toHaveBeenCalledWith('来源.xlsx', buffer, 'hxg')
    expect(mock.instances).toHaveLength(0)
  })

  it('can cancel a scheduled fallback before it reads the file', async () => {
    vi.useFakeTimers()
    vi.stubGlobal('Worker', undefined)
    const result = parseCodexOffThread('待取消.xlsx', new ArrayBuffer(1)).catch((error) => error)
    cancelCodexParsing()
    await vi.runAllTimersAsync()
    expect((await result).name).toBe('AbortError')
    expect(mock.analyze).not.toHaveBeenCalled()
  })
})
