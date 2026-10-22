import { shallowRef, type Component } from 'vue'
import type { Router, RouteLocationNormalized, NavigationFailure } from 'vue-router'
import { classifyNavigation, factoryQueryChanged, routeVisualIdentity, type MotionKind } from './classifyNavigation'

export interface EntryOrigin {
  icon: Component
  accent: string
  soft: string
  rect: { x: number; y: number; width: number; height: number } | null
  viewport: [number, number]
  triggerId: string
  homeId: string
  homePath: string
  historyPosition: number | null
  scroll: [number, number, number, number]
  expectedId: string
  expectedPath: string
  context: string
}
export interface MotionCommit {
  token: number
  to: RouteLocationNormalized
  from: RouteLocationNormalized
  kind: MotionKind
  origin: EntryOrigin | null
  context: string
}

export function createRouteMotionNavigation(router: Router) {
  let sequence = 0
  let queued: { token: number; origin: EntryOrigin } | null = null
  const attempts = new WeakMap<RouteLocationNormalized, number>()
  const listeners = new Set<(commit: MotionCommit | null) => void>()
  let context = () => ''
  let enabled = () => false
  const entry = shallowRef<MotionCommit | null>(null)
  const emit = (value: MotionCommit | null) => { for (const listener of listeners) listener(value) }
  function cancelVisuals() { sequence++; queued = null; emit(null) }
  function invalidate() { cancelVisuals(); entry.value = null }
  function recordIntent(origin: EntryOrigin) {
    cancelVisuals()
    queued = { token: sequence, origin }
    return sequence
  }
  function matches(to: RouteLocationNormalized, origin: EntryOrigin) {
    return to.fullPath === origin.expectedPath || to.redirectedFrom?.fullPath === origin.expectedPath
  }
  const removeBefore = router.beforeEach(to => {
    if (queued && matches(to, queued.origin) && queued.origin.context === context()) {
      attempts.set(to, queued.token)
      emit(null)
    } else {
      queued = null
      attempts.set(to, ++sequence)
      emit(null)
    }
  })
  function tokenFor(to: RouteLocationNormalized) {
    return attempts.get(to) ?? (queued && matches(to, queued.origin) ? queued.token : undefined)
  }
  function settle(to: RouteLocationNormalized, from: RouteLocationNormalized, failure?: NavigationFailure | unknown) {
    const token = tokenFor(to)
    // A late cancelled navigation (or its error/finally) cannot touch the winner.
    if (token !== sequence) return
    const origin = queued?.token === token ? queued.origin : null
    queued = null
    if (failure) { emit(null); return }
    const kind = classifyNavigation(to, from)
    if (factoryQueryChanged(to, from) || !routeVisualIdentity(to).eligible) entry.value = null
    const commit: MotionCommit = {
      token, to, from, kind, context: context(),
      origin: origin?.expectedId === routeVisualIdentity(to).id && origin.context === context() ? origin : null,
    }
    // Persist the initial ownership through delayed API rendering. A same-family
    // query refresh does not turn a late first page into another entrance.
    if (kind !== 'none' || routeVisualIdentity(to).id !== routeVisualIdentity(from).id) {
      entry.value = enabled() && kind !== 'none' ? commit : null
    }
    emit(commit)
  }
  const removeAfter = router.afterEach((to, from, failure) => settle(to, from, failure))
  const removeError = router.onError((error, to, from) => settle(to, from, error))
  return {
    entry, recordIntent, invalidate, cancelVisuals,
    isCurrent: (token: number) => token === sequence,
    attach(readContext: () => string, readEnabled: () => boolean, listener: (commit: MotionCommit | null) => void) {
      context = readContext; enabled = readEnabled; listeners.add(listener)
      return () => { listeners.delete(listener); context = () => ''; enabled = () => false; invalidate() }
    },
    dispose() { invalidate(); removeBefore(); removeAfter(); removeError(); listeners.clear() },
  }
}
export type RouteMotionNavigation = ReturnType<typeof createRouteMotionNavigation>
const installations = new WeakMap<Router, RouteMotionNavigation>()
export function installRouteMotionNavigation(router: Router) {
  let navigation = installations.get(router)
  if (!navigation) { navigation = createRouteMotionNavigation(router); installations.set(router, navigation) }
  return navigation
}
