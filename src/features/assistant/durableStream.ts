import { parseSSE } from './stream'

export class EventGapError extends Error {}
export class RunUnavailableError extends Error {}

/** This reader knows only GET subscriptions. It cannot admit or retry a run. */
export async function readDurableEvents(response: Response, cursor: () => number,
  accept: (event: string, data: Record<string, unknown>) => void, signal: AbortSignal) {
  if (!response.body) throw new Error('未收到运行订阅。')
  let count = 0
  for await (const frame of parseSSE(response.body)) {
    if (signal.aborted) return count
    const data = JSON.parse(frame.data) as Record<string, unknown>
    if (frame.event === 'run.unavailable') throw new RunUnavailableError('相关资料权限已改变，当前内容已清除。')
    const seq = Number(data.seq)
    if (!Number.isSafeInteger(seq) || seq <= 0) throw new EventGapError('订阅序号无效。')
    if (seq <= cursor()) continue
    if (seq !== cursor() + 1) throw new EventGapError('订阅进度有缺口，需要读取保存进度。')
    accept(frame.event, data)
    count++
    if (/^run\.(completed|cancelled|interrupted|failed)$/.test(frame.event)) return count
  }
  return count
}

export function subscriptionDelay(ms: number, signal: AbortSignal) {
  return new Promise<void>(resolve => {
    if (signal.aborted) { resolve(); return }
    const done = () => { clearTimeout(timer); signal.removeEventListener('abort', done); resolve() }
    const timer = setTimeout(done, ms)
    signal.addEventListener('abort', done, { once: true })
  })
}
