import { onBeforeUnmount, ref, watch } from 'vue'
import type { SheetDownloadOptions } from '@/api/collaborativeSheets'
import { getApiErrorMessageAsync } from '@/lib/http'
import { getAuthenticationGeneration } from '@/lib/authenticationGeneration'
import { createRandomUuid } from '@/lib/randomUuid'

export interface DownloadContext { id: string; factory: string; account: string; name: string }
export function useSheetDownload(
  context: () => DownloadContext | undefined,
  prepare: (current: () => boolean) => Promise<boolean>,
  fetch: (target: DownloadContext, progress: (loaded: number, total?: number) => void, options: SheetDownloadOptions) => Promise<Blob>,
) {
  const active = ref(false), status = ref(''), error = ref(''), readyUrl = ref(''), readyName = ref('')
  let run = 0, controller: AbortController | undefined, release: (() => void) | undefined, disposed = false
  let revokeTimer: ReturnType<typeof setTimeout> | undefined
  function clearFile() {
    clearTimeout(revokeTimer)
    if (readyUrl.value) URL.revokeObjectURL(readyUrl.value)
    readyUrl.value = ''; readyName.value = ''
  }
  function cancel(message = '下载已取消，可重试；已保存的填写不受影响。') {
    run++; controller?.abort(); controller = undefined; release?.(); release = undefined
    active.value = false; status.value = message; error.value = ''; clearFile()
  }
  function reset() { cancel('') }
  // A -> B -> A invalidates the old operation even when its eventual ID matches.
  watch(() => { const c = context(); return c ? JSON.stringify([c.id, c.factory, c.account]) : '' }, reset, { flush: 'sync' })
  function handoff() {
    if (!readyUrl.value) return
    const anchor = document.createElement('a')
    anchor.href = readyUrl.value; anchor.download = readyName.value
    document.body.appendChild(anchor)
    try { anchor.click() } finally { anchor.remove() }
  }
  async function start() {
    const target = context()
    if (!target || active.value || disposed) return
    clearFile(); error.value = ''; active.value = true; status.value = '正在确认填写…'
    const token = ++run, auth = getAuthenticationGeneration(), began = performance.now()
    const abort = new AbortController(); controller = abort
    let timedOut = false
    const owns = () => !disposed && token === run
    const current = () => owns() && !timedOut && auth === getAuthenticationGeneration()
    const requestId = createRandomUuid()
    const trace = (phase: string, info = {}) => console.info('[collaborative-download]', JSON.stringify({ phase, elapsed_ms: Math.round(performance.now() - began), request_id: requestId, ...info }))
    let deadline: ReturnType<typeof setTimeout> | undefined
    const interrupted = new Promise<never>((_, reject) => { release = () => reject(new Error('cancelled')) })
    function bounded<T>(operation: Promise<T>, ms: number, message: string): Promise<T> {
      clearTimeout(deadline)
      const timeout = new Promise<never>((_, reject) => { deadline = setTimeout(() => { timedOut = true; reject(new Error(message)); abort.abort() }, ms) })
      return Promise.race([operation, timeout, interrupted]).finally(() => clearTimeout(deadline))
    }
    try {
      trace('prepare')
      const prepared = await bounded(prepare(current), 30_000, '确认填写超时，请按 Enter 确认当前单元格，待保存完成后重试。')
      if (!current()) return
      if (!prepared) throw new Error('填写尚未保存，请先处理同步提示再下载。')
      status.value = '正在生成汇总…'; trace('request')
      const blob = await bounded(fetch(target, (loaded, total) => {
        if (current()) status.value = total ? `正在下载 ${Math.min(100, Math.round(loaded / total * 100))}%` : `正在下载 ${(loaded / 1024 / 1024).toFixed(1)} MB`
      }, { signal: abort.signal, requestId, onResponse: info => { if (current()) trace('response', info) } }), 300_000, '下载超时，请检查网络后重试；已保存的填写不受影响。')
      if (!current()) return
      readyUrl.value = URL.createObjectURL(blob)
      readyName.value = target.name.replace(/(\.[^.]+)$/, '-已填写$1')
      // Keep a fresh user-clickable link if automatic downloads are blocked or
      // the browser still requires a save action after receiving the bytes.
      revokeTimer = setTimeout(() => { clearFile(); status.value = '文件已交给浏览器。再次保存入口已过期，需要时请重新下载。' }, 300_000)
      handoff(); trace('browser_handoff', { bytes: blob.size })
      status.value = '文件已接收并交给浏览器；未出现保存提示时，可点击“再次保存文件”。'
    } catch (reason) {
      if (!owns() || auth !== getAuthenticationGeneration()) return
      const message = reason instanceof Error && !('response' in reason) ? reason.message : await getApiErrorMessageAsync(reason)
      if (!owns() || auth !== getAuthenticationGeneration()) return
      error.value = message; status.value = '下载未完成，可重试；填写内容仍保留。'; trace('failed')
    } finally {
      clearTimeout(deadline)
      if (owns()) { active.value = false; controller = undefined; release = undefined }
    }
  }
  function authChanged() { cancel('登录账号已变化，下载已取消。') }
  window.addEventListener('auth-session-boundary-changed', authChanged)
  onBeforeUnmount(() => { disposed = true; reset(); window.removeEventListener('auth-session-boundary-changed', authChanged) })
  return { active, status, error, readyUrl, readyName, start, cancel, handoff }
}
