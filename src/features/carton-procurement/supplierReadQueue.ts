import type { InjectionKey } from 'vue'

export function createSupplierReadQueue(limit = 2) {
  let active = 0
  const pending: (() => void)[] = []
  function next() { while (active < limit && pending.length) pending.shift()!() }
  return {
    run<T>(read: () => Promise<T>, signal?: AbortSignal): Promise<T> {
      return new Promise((resolve, reject) => {
        const cancelled = () => new DOMException('读取已取消', 'AbortError')
        const start = () => {
          signal?.removeEventListener('abort', abort)
          if (signal?.aborted) { reject(cancelled()); return }
          active++
          Promise.resolve().then(read).then(resolve, reject).finally(() => { active--; next() })
        }
        const abort = () => {
          const index = pending.indexOf(start)
          if (index >= 0) { pending.splice(index, 1); reject(cancelled()) }
        }
        if (signal?.aborted) { reject(cancelled()); return }
        signal?.addEventListener('abort', abort, { once: true })
        pending.push(start); next()
      })
    },
  }
}

export const supplierReadQueueKey: InjectionKey<ReturnType<typeof createSupplierReadQueue>> = Symbol('supplier-read-queue')
