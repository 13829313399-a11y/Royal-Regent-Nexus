import CodexParseWorker from './codexParse.worker.js?worker&inline'
import { analyzeCodexFile } from './codexImport.js'

let worker = null
let sequence = 0
const pending = new Map()

function abortError() {
  const error = new Error('已取消解析')
  error.name = 'AbortError'
  return error
}

function finish(id, ok, value) {
  const task = pending.get(id)
  if (!task) return
  pending.delete(id)
  if (task.timer !== undefined) clearTimeout(task.timer)
  if (ok) task.resolve(value)
  else task.reject(value instanceof Error ? value : new Error(String(value || '解析失败')))
}

function resetWorker(error) {
  const previous = worker
  worker = null
  if (previous) {
    previous.onmessage = null
    previous.onerror = null
    previous.onmessageerror = null
    previous.terminate()
  }
  for (const id of [...pending.keys()]) finish(id, false, error)
}

function getWorker() {
  if (typeof Worker === 'undefined') return null
  if (worker) return worker
  try {
    const next = new CodexParseWorker()
    next.onmessage = ({ data }) => {
      const { id, ok, result, error } = data || {}
      finish(id, ok, ok ? result : new Error(error || '解析失败'))
    }
    next.onerror = () => resetWorker(new Error('后台解析失败，请重试或重新打开文件'))
    next.onmessageerror = () => resetWorker(new Error('后台解析结果无法读取，请重试'))
    worker = next
    return worker
  } catch {
    return null
  }
}

/**
 * 后台分析源表。保留传入的 buffer，供后续重新识别与生成使用；不转移原 buffer。
 * 不支持 Worker 的环境回退到同一解析函数，开始前仍可以取消。
 */
export function parseCodexOffThread(fileName, buffer, kind = 'auto') {
  const current = getWorker()
  return new Promise((resolve, reject) => {
    const id = ++sequence
    const task = { resolve, reject, timer: undefined }
    pending.set(id, task)
    if (current) {
      try {
        current.postMessage({ id, fileName, buffer, kind })
      } catch (error) {
        finish(id, false, error)
      }
      return
    }
    task.timer = setTimeout(async () => {
      if (!pending.has(id)) return
      try {
        const result = await analyzeCodexFile(fileName, buffer, kind)
        finish(id, true, result)
      } catch (error) {
        finish(id, false, error)
      }
    }, 0)
  })
}

/** 终止当前后台线程及所有待解析任务；下一次解析自动创建新线程。 */
export function cancelCodexParsing() {
  resetWorker(abortError())
}
