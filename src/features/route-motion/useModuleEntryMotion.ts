import { computed, inject, provide, type Component, type InjectionKey } from 'vue'
import type { RouteLocationRaw, Router } from 'vue-router'

export interface EntryVisual { id: string; icon: Component }
export interface RouteMotionContext {
  record(event: MouseEvent | KeyboardEvent, visual: EntryVisual, to: RouteLocationRaw): void
  ownsEntry(): boolean
}
export const routeMotionKey: InjectionKey<RouteMotionContext> = Symbol('route-motion')

/** Mirrors native link semantics; capture phase runs before RouterLink prevents default. */
export function acceptsEntryActivation(event: MouseEvent | KeyboardEvent) {
  const link = event.currentTarget instanceof Element ? event.currentTarget.closest('a') : null
  return !event.defaultPrevented && !event.altKey && !event.ctrlKey && !event.metaKey && !event.shiftKey
    && (!('button' in event) || event.button === 0)
    && !link?.hasAttribute('download') && (!link?.getAttribute('target') || link.getAttribute('target') === '_self')
}

export function useModuleEntryMotion() {
  const context = inject(routeMotionKey, null)
  return (event: MouseEvent | KeyboardEvent, visual: EntryVisual, to: RouteLocationRaw | undefined) => {
    if (to && acceptsEntryActivation(event)) context?.record(event, visual, to)
  }
}

// Resolve static/function redirects for presentation only. Actual navigation and
// guards still run exactly once through the original RouterLink/router.push.
export function resolveMotionDestination(router: Router, to: RouteLocationRaw) {
  let target = router.resolve(to)
  for (let i = 0; i < 8; i++) {
    const redirect = target.matched.at(-1)?.redirect
    if (!redirect) break
    const next = typeof redirect === 'function' ? redirect(target, router.currentRoute.value) : redirect
    target = router.resolve(typeof next === 'string' ? next : { query: target.query, hash: target.hash, ...next })
  }
  return target
}

export function useRouteEntryOwned() { return inject(routeMotionKey, null)?.ownsEntry() ?? false }
export function useRouteEntryOwnership() {
  const context = inject(routeMotionKey, null)
  return computed(() => context?.ownsEntry() ?? false)
}

const localEntryKey: InjectionKey<() => boolean> = Symbol('module-first-entry')
/** Keep first-entry ownership through delayed API loading, without caching business state. */
export function provideModuleEntryOwnership() {
  const owned = useRouteEntryOwned()
  let consumed = false
  provide(localEntryKey, () => {
    if (consumed) return false
    consumed = true
    return owned
  })
  return owned
}
export function consumeModuleEntryOwnership() { return inject(localEntryKey, () => false)() }
