import type { useAuthStore } from '@/stores/auth'
import { getAuthenticationGeneration } from '@/lib/authenticationGeneration'

type Auth = Pick<ReturnType<typeof useAuthStore>, 'currentUser' | 'authorizationVersion' | 'can'>
export const threeDCanRead = (auth: Auth) => ['three-d-printing', 'production', 'management']
  .some(department => auth.can('three_d_printing:read', 'huakang-a', department))
export const threeDScopeKey = (auth: Auth) => JSON.stringify([
  auth.currentUser?.id, auth.currentUser?.identity?.employment_epoch,
  auth.authorizationVersion, getAuthenticationGeneration(),
])

let guard: (() => boolean) | null = null
const editors = new Set<() => boolean>()
export function registerThreeDEditor(blocks: () => boolean) {
  editors.add(blocks)
  return () => { editors.delete(blocks) }
}
export const threeDEditorBlocks = () => [...editors].some(blocks => blocks())
export function registerThreeDNavigationGuard(value: () => boolean) {
  guard = value
  return () => { if (guard === value) guard = null }
}
export function guardThreeDNavigation(to: { fullPath: string; name?: unknown }, from: { fullPath: string }) {
  if (to.fullPath === from.fullPath || to.name === 'login' || to.name === 'change-password') return true
  return guard?.() ?? true
}
