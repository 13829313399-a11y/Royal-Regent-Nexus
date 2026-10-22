import { computed, markRaw, nextTick, onBeforeUnmount, onMounted, provide, shallowRef, watch, type Component } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import type { HomeAppearance } from '@/composables/useHomeAppearance'
import { getAuthenticationGeneration } from '@/lib/authenticationGeneration'
import { createRouteMotionCoordinator } from './createRouteMotionCoordinator'
import { installRouteMotionNavigation, type EntryOrigin, type MotionCommit } from './navigation'
import { factoryQueryChanged, routeVisualIdentity } from './classifyNavigation'
import { resolveMotionDestination, routeMotionKey } from './useModuleEntryMotion'

export interface RouteGhost { token: number; icon: Component; accent: string; soft: string; x: number; y: number }
const easing = 'cubic-bezier(0.16, 1, 0.3, 1)'
const visibleRect = (element: Element | null) => {
  if (!element?.isConnected) return null
  const rect = element.getBoundingClientRect()
  return rect.width > 0 && rect.height > 0 && rect.x >= 0 && rect.y >= 0 && rect.right <= innerWidth && rect.bottom <= innerHeight
    ? { x: rect.x, y: rect.y, width: rect.width, height: rect.height } : null
}

export function useRouteMotionHost(appearance: HomeAppearance, getSurface: () => HTMLElement | null) {
  const router = useRouter(), auth = useAuthStore(), app = useAppStore()
  const navigation = installRouteMotionNavigation(router), effects = createRouteMotionCoordinator()
  const ghost = shallowRef<RouteGhost | null>(null)
  const returns = new Map<string, EntryOrigin>()
  const featureEnabled = import.meta.env.VITE_ROUTE_MOTION_ENABLED !== 'false'
  const allowed = () => featureEnabled && appearance.effectiveMotion.value !== 'off' && !document.hidden
  const context = computed(() => {
    const { server_now: _clock, ...identity } = auth.currentUser?.identity ?? {}
    return JSON.stringify([auth.currentUser?.id, identity, auth.authorizationVersion, auth.isAuthenticated,
      auth.permissions, auth.grants, auth.effectiveAccess, auth.authzMode, auth.hasEffectiveAccessSnapshot, auth.factoryScopes, auth.departmentScopes,
      app.activeFactoryId, app.activeProductionFactory.id])
  })
  const contextStamp = () => `${getAuthenticationGeneration()}:${context.value}`
  function cancel() { effects.cancel(); ghost.value = null }
  function clearContext() { returns.clear(); navigation.invalidate() }
  function remember(origin: EntryOrigin) {
    const key = `${origin.homeId}:${origin.historyPosition}`
    returns.delete(key); returns.set(key, origin)
    if (returns.size > 12) returns.delete(returns.keys().next().value!)
  }
  function returnOrigin(commit: MotionCommit) {
    const homeId = routeVisualIdentity(commit.to).id
    const position = window.history.state?.position
    const candidates = [...returns.values()].filter(value => value.homeId === homeId && value.context === contextStamp())
    return candidates.find(value => value.historyPosition === position) ?? candidates.at(-1)
  }
  function findTrigger(origin: EntryOrigin) {
    return [...document.querySelectorAll<HTMLElement>('[data-route-entry-id]')]
      .find(element => element.dataset.routeEntryId === origin.triggerId && element.getClientRects().length) ?? null
  }
  function focusOnce(target: HTMLElement | null) {
    if (!target || document.querySelector('dialog[open], [role="dialog"][data-state="open"]')) return
    const active = document.activeElement
    // Local dialogs/editors and deliberate focus changes take priority.
    if (active instanceof HTMLElement && active !== document.body && active.isConnected && active !== target) return
    if (!target.hasAttribute('tabindex') && !target.matches('a, button, input, select, textarea')) target.setAttribute('tabindex', '-1')
    target.focus({ preventScroll: true })
  }
  async function play(commit: MotionCommit | null) {
    cancel()
    if (!commit) return
    if (factoryQueryChanged(commit.to, commit.from) || !routeVisualIdentity(commit.to).eligible) returns.clear()
    if (commit.kind === 'none') return
    if (commit.origin) remember(commit.origin)
    const deadline = performance.now() + 340
    const remaining = () => Math.max(0, deadline - performance.now())
    const token = effects.begin()
    const current = () => effects.current(token) && navigation.isCurrent(commit.token)
      && router.currentRoute.value.fullPath === commit.to.fullPath && commit.context === contextStamp()
    await nextTick()
    if (!current()) return
    if (commit.kind === 'module-to-home' && typeof requestAnimationFrame === 'function') {
      // Native history scroll restoration runs after popstate's microtasks.
      // Restore once on the next frame, without delaying the route's mount.
      await new Promise<void>(resolve => {
        let disown = () => {}
        const frame = requestAnimationFrame(() => { disown(); resolve() })
        disown = effects.own(token, () => { cancelAnimationFrame(frame); resolve() })
      })
      if (!current()) return
    }
    const surface = getSurface()
    if (!surface?.isConnected) return
    let returning: EntryOrigin | undefined
    let returnTrigger: HTMLElement | null = null
    if (commit.kind === 'module-to-home') {
      returning = returnOrigin(commit)
      if (returning) {
        // DOM is committed before restoring; never turn this into smooth scrolling.
        window.scrollTo({ left: returning.scroll[0], top: returning.scroll[1], behavior: 'instant' })
        const main = document.getElementById('app-content')
        if (main) { main.scrollLeft = returning.scroll[2]; main.scrollTop = returning.scroll[3] }
        returnTrigger = findTrigger(returning)
      }
      const visibleTrigger = returnTrigger && visibleRect(returnTrigger.querySelector('[data-route-entry-icon]') ?? returnTrigger)
      if (returning && !visibleTrigger) {
        // Search/filter changes can move a still-existing card off screen.
        // Do not restore invisible keyboard focus or reuse its old coordinates.
        returnTrigger = null
        window.scrollTo({ left: 0, top: 0, behavior: 'instant' })
      }
      focusOnce(returnTrigger ?? surface.querySelector<HTMLElement>('h1') ?? document.getElementById('home-module-search'))
    } else {
      if (commit.kind === 'home-to-module' || commit.kind === 'home-to-department') {
        window.scrollTo({ left: 0, top: 0, behavior: 'instant' })
      }
      focusOnce(surface.querySelector<HTMLElement>('h1') ?? surface)
    }
    if (!allowed() || !remaining()) return
    const duration = appearance.effectiveMotion.value === 'calm' ? 140 : commit.kind === 'module-to-home' ? 260 : 180
    const origin = returning ?? commit.origin
    const anchor = returning
      ? returnTrigger?.querySelector('[data-route-entry-icon]') ?? returnTrigger
      : surface.querySelector('[data-route-motion-anchor]')
    const destination = visibleRect(anchor ?? null)
    // Measure once before animation writes; never read layout on animation frames.
    // Opacity only: no containing-block changes for fixed/sticky or virtual rows.
    effects.animate(token, surface, [{ opacity: 0.55 }, { opacity: 1 }], { duration: Math.min(duration, remaining()), easing })
    if (appearance.effectiveMotion.value === 'expressive' && origin?.rect && destination
        && origin.viewport[0] === innerWidth && origin.viewport[1] === innerHeight
        && (returning || commit.kind === 'home-to-module' || commit.kind === 'home-to-department')) {
      const end = { x: destination.x + (Math.min(destination.width, 40) - 40) / 2, y: destination.y + (destination.height - 40) / 2 }
      const source = returning ? { x: end.x, y: end.y + 6 } : { x: origin.rect.x, y: origin.rect.y }
      const distance = Math.hypot(end.x - source.x, end.y - source.y)
      // Far-apart layouts use a six-pixel local arrival instead of flying over data.
      const start = distance > 280 ? { x: end.x, y: end.y + 6 } : source
      ghost.value = { token, icon: markRaw(origin.icon), accent: origin.accent, soft: origin.soft, ...end }
      await nextTick()
      if (!current() || !allowed()) return
      if (!remaining()) { cancel(); return }
      const badge = document.querySelector<HTMLElement>(`[data-route-motion-ghost="${token}"]`)
      if (badge) {
        effects.animate(token, badge, [
          { transform: `translate(${start.x - end.x}px, ${start.y - end.y}px) scale(1)`, opacity: 0.9 },
          { transform: 'translate(0, 0) scale(0.9)', opacity: 0 },
        ], { duration: Math.min(returning ? 260 : 280, remaining()), easing })
        const halo = badge.querySelector<HTMLElement>('.rr-route-motion__surface')
        if (halo) effects.animate(token, halo, [{ transform: 'scale(0.85)', opacity: 0.65 }, { transform: 'scale(1.35)', opacity: 0 }], { duration: Math.min(180, remaining()), easing })
      }
    }
    if (!current()) return
    // Cleanup only; this timer never delays mount, input, navigation, or requests.
    // Budget starts at route confirmation, not after rendering. Leave one frame
    // of headroom under the 360ms contract and skip late decoration entirely.
    const timer = window.setTimeout(() => { if (current()) cancel() }, remaining())
    effects.own(token, () => window.clearTimeout(timer))
  }
  // An enabled coordinator also owns a deliberately silent entry. Otherwise
  // choosing "off" would resurrect each module's independent first reveal.
  const detach = navigation.attach(contextStamp, () => featureEnabled, commit => {
    void play(commit).catch(() => { if (!commit || navigation.isCurrent(commit.token)) cancel() })
  })
  provide(routeMotionKey, {
    ownsEntry: () => {
      const entry = navigation.entry.value
      return Boolean(entry && entry.context === contextStamp() && entry.to.path === router.currentRoute.value.path)
    },
    record(event, visual, to) {
      const from = router.currentRoute.value
      const home = routeVisualIdentity(from)
      // Sidebar clicks still cancel previous visual work, but only actual home
      // entries carry a source badge. Native links and guards remain authoritative.
      if (!home.home) { navigation.invalidate(); return }
      const trigger = event.currentTarget instanceof HTMLElement ? event.currentTarget : null
      const container = trigger?.closest('[data-route-entry-id]') ?? trigger
      const icon = container?.querySelector('[data-route-entry-icon]') ?? trigger
      const style = icon ? getComputedStyle(icon) : null
      const destination = resolveMotionDestination(router, to)
      const main = document.getElementById('app-content')
      const origin: EntryOrigin = {
        icon: markRaw(visual.icon), accent: style?.color ?? '#0f766e',
        soft: style?.getPropertyValue('--home-soft').trim() || '#e5f5f2', rect: visibleRect(icon ?? null),
        viewport: [innerWidth, innerHeight], triggerId: container instanceof HTMLElement ? container.dataset.routeEntryId ?? visual.id : visual.id,
        homeId: home.id, homePath: from.fullPath, historyPosition: window.history.state?.position ?? null,
        scroll: [window.scrollX, window.scrollY, main?.scrollLeft ?? 0, main?.scrollTop ?? 0],
        expectedId: routeVisualIdentity(destination).id, expectedPath: router.resolve(to).fullPath, context: contextStamp(),
      }
      navigation.recordIntent(origin)
      if (allowed() && trigger) {
        const token = effects.begin()
        effects.animate(token, trigger, [{ transform: 'scale(0.985)' }, { transform: 'scale(1)' }], { duration: 120, easing })
      }
    },
  })
  watch(context, clearContext, { flush: 'sync' })
  // A preference change cancels paint, not a legitimate in-flight navigation.
  watch(appearance.effectiveMotion, cancel, { flush: 'sync' })
  onMounted(() => {
    window.addEventListener('resize', cancel)
    window.addEventListener('auth-session-boundary-changed', clearContext)
  })
  onBeforeUnmount(() => {
    detach(); effects.dispose(); ghost.value = null; returns.clear()
    window.removeEventListener('resize', cancel)
    window.removeEventListener('auth-session-boundary-changed', clearContext)
  })
  return { ghost }
}
