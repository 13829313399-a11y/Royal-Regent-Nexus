import { readonly, ref, shallowRef } from 'vue'
import type { Router, RouteLocationNormalized } from 'vue-router'
import { CUTTING_BASE, CUTTING_WORKSPACES, isCuttingFactory } from './navigation'

interface ResourceFailure { target: string; title: string }
const resourceError = /failed to fetch dynamically imported module|importing a module script failed|error loading dynamically imported module|unable to preload css|loading (?:css )?chunk .+ failed|css_chunk_load_failed/i

// Eagerly installed outside the lazy workspace: its CSS/error UI must not depend
// on the resource whose navigation failed. Never retry a poisoned import in place.
export function installCuttingResourceRecovery(router: Router, navigate = (target: string) => window.location.assign(target)) {
  const failure = shallowRef<ResourceFailure>(), feedback = ref(''), reloading = ref(false)
  const attempts = new WeakMap<RouteLocationNormalized, number>()
  let sequence = 0, tainted = false
  const targetFor = (to: RouteLocationNormalized): ResourceFailure | undefined => {
    if (!(to.path === CUTTING_BASE || to.path.startsWith(`${CUTTING_BASE}/`)) || !isCuttingFactory(to.query.factory)) return
    return { target: to.fullPath, title: CUTTING_WORKSPACES.find(w => to.path === `${CUTTING_BASE}/${w.path}`)?.title ?? '裁床部' }
  }
  function clear() { sequence++; failure.value = undefined; feedback.value = ''; reloading.value = false }
  const removeBefore = router.beforeEach(to => {
    attempts.set(to, ++sequence)
    failure.value = undefined; feedback.value = ''; reloading.value = false
    const target = targetFor(to)
    // A failed CSS preload can be cached as "already requested" even when a
    // later JS import succeeds. Keep the old page intact until an explicit reload.
    if (target && tainted) { failure.value = target; return false }
  })
  const removeError = router.onError((error, to) => {
    if (attempts.get(to) !== sequence || !resourceError.test(error instanceof Error ? error.message : String(error))) return
    const target = targetFor(to)
    if (target) { tainted = true; failure.value = target; feedback.value = ''; reloading.value = false }
  })
  function reload() {
    const target = failure.value
    if (!target || reloading.value) return
    if (!navigator.onLine) { feedback.value = '当前仍处于离线状态。请恢复网络后重试，页面未重新加载。'; return }
    // Reuse existing dirty/unknown-write protections before leaving the document.
    // Do not dispatch writes, bypass guards or restore a prior user's workspace.
    const guard = new Event('beforeunload', { cancelable: true })
    if (!window.dispatchEvent(guard)) {
      feedback.value = '当前页面有未保存内容或待核实操作，请先处理后再重新加载。'
      return
    }
    reloading.value = true; feedback.value = '正在重新加载目标页面…'
    try { navigate(target.target) }
    catch { reloading.value = false; feedback.value = '未能重新加载页面，请检查网络后重试。' }
  }
  window.addEventListener('auth-session-boundary-changed', clear)
  window.addEventListener('authorization-context-changed', clear)
  return {
    failure: readonly(failure), feedback: readonly(feedback), reloading: readonly(reloading), reload,
    dispose() {
      clear(); removeBefore(); removeError()
      window.removeEventListener('auth-session-boundary-changed', clear)
      window.removeEventListener('authorization-context-changed', clear)
    },
  }
}
