import { ref } from 'vue'

type Surface = 'directory' | 'account' | 'messages' | 'assistant'
export const foregroundSurface = ref<Surface | null>(null)
export const businessPreempted = ref(false)
const closers = new Map<Surface, () => void>()
let version = 0
export function registerSurface(name: Surface, close: () => void) { closers.set(name, close); return () => { closers.delete(name); releaseSurface(name) } }
export function requestSurface(name: Surface, intent: 'explicit' | 'hover' = 'explicit') {
  if (businessPreempted.value || (intent === 'hover' && foregroundSurface.value && foregroundSurface.value !== name)) return false
  version += 1
  if (foregroundSurface.value && foregroundSurface.value !== name) closers.get(foregroundSurface.value)?.()
  foregroundSurface.value = name
  return true
}
export function releaseSurface(name: Surface) { if (foregroundSurface.value === name) { foregroundSurface.value = null; version += 1 } }
export function preemptSurface(active: boolean) {
  businessPreempted.value = active
  if (active) { version += 1; if (foregroundSurface.value) closers.get(foregroundSurface.value)?.(); foregroundSurface.value = null }
}
export function surfaceVersion() { return version }
