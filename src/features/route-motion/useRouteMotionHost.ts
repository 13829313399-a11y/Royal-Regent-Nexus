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
import { historyPoint, matchReturn, rememberEntry, type ReturnEntry } from './returnHistory'
import { sameAnchors, sourceAnchors, targetAnchors, visibleAnchorRect, type AnchorSnapshot } from './spatialAnchors'
import { readViewport, sameViewport } from './spatialGeometry'
import { createSpatialRenderer } from './spatialRenderer'

export interface RouteGhost { token: number; icon: Component; accent: string; soft: string; x: number; y: number }
const easing = 'cubic-bezier(0.16, 1, 0.3, 1)'
const visibleRect = (element: Element | null) => {
  if (!element?.isConnected) return null
  const rect = element.getBoundingClientRect()
  return rect.width > 0 && rect.height > 0 && rect.x >= 0 && rect.y >= 0 && rect.right <= innerWidth && rect.bottom <= innerHeight
    ? { x: rect.x, y: rect.y, width: rect.width, height: rect.height } : null
}

export function useRouteMotionHost(appearance: HomeAppearance, getSurface: (fullPage: boolean) => HTMLElement | null,
  getLayer: () => HTMLElement | null) {
  const router = useRouter(), auth = useAuthStore(), app = useAppStore()
  const navigation = installRouteMotionNavigation(router), effects = createRouteMotionCoordinator()
  const ghost = shallowRef<RouteGhost | null>(null)
  const featureEnabled = import.meta.env.VITE_ROUTE_MOTION_ENABLED !== 'false'
  const spatialEnabled = featureEnabled && import.meta.env.VITE_ROUTE_MOTION_V2_ENABLED === 'true'
  const renderer = createSpatialRenderer(effects, getLayer)
  let returns: ReturnEntry[] = []
  let revision = 0
  let inputRevision = 0
  let viewport = readViewport()
  const allowed = () => featureEnabled && appearance.effectiveMotion.value !== 'off' && !document.hidden
  const context = computed(() => {
    const { server_now: _clock, ...identity } = auth.currentUser?.identity ?? {}
    return JSON.stringify([auth.currentUser?.id, identity, auth.authorizationVersion, auth.isAuthenticated,
      auth.permissions, auth.grants, auth.effectiveAccess, auth.authzMode, auth.hasEffectiveAccessSnapshot, auth.factoryScopes, auth.departmentScopes,
      app.activeFactoryId, app.activeProductionFactory.id])
  })
  const contextStamp = () => `${getAuthenticationGeneration()}:${context.value}`
  function cancel() { effects.cancel(); ghost.value = null }
  function clearContext() { returns.length = 0; navigation.invalidate() }
  function interrupt() { revision++; cancel() }
  function userInput() { inputRevision++; interrupt() }
  function resized() {
    viewport = readViewport()
    for (const entry of returns) entry.origin = { ...entry.origin, spatial: undefined }
    interrupt()
  }
  function visualViewportChanged() {
    if (!sameViewport(viewport, readViewport())) resized()
  }
  function findTrigger(origin: EntryOrigin, surface: HTMLElement) {
    const scope = spatialEnabled ? surface : document
    const matches = [...scope.querySelectorAll<HTMLElement>('[data-route-entry-id]')]
      .filter(element => element.dataset.routeEntryId === origin.triggerId && element.getClientRects().length)
    if (spatialEnabled) {
      const declared = matches.filter(el => el.matches('[data-rr-motion-source="surface"]'))
      if (declared.length) return declared.length === 1 ? declared[0]! : null
      if (matches.length !== 1) return null
    }
    return matches[0] ?? null
  }
  function confirmedSource(origin: EntryOrigin, scope: HTMLElement | null, now: number) {
    const capture = origin.spatial
    if (!capture || capture.revision !== revision || now - capture.captured > 900 || !sameViewport(capture.view, readViewport())) return null
    const main = document.getElementById('app-content')
    const scroll = [window.scrollX, window.scrollY, main?.scrollLeft ?? 0, main?.scrollTop ?? 0]
    if (scroll.some((value, i) => Math.abs(value - origin.scroll[i]!) >= 1)) return null
    const source = sourceAnchors(scope, origin.triggerId, capture.view, undefined, capture.compact)
    return source && sameAnchors(capture.anchors, source.snapshot) ? source.snapshot : null
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
    const toId = routeVisualIdentity(commit.to), fromId = routeVisualIdentity(commit.from)
    const point = historyPoint()
    if (commit.silentRedirect || factoryQueryChanged(commit.to, commit.from) || !toId.eligible) returns.length = 0
    if (spatialEnabled && commit.traversalDelta === undefined && point.position !== null && commit.from.fullPath !== commit.to.fullPath) {
      // Pushing or replacing a history entry invalidates its previous forward branch.
      const position = point.position
      returns = returns.filter(entry => entry.position !== null && entry.position < position)
    }
    if (commit.kind === 'none') return
    const committedAt = performance.now()
    const candidates = toId.home && (!spatialEnabled || commit.traversalDelta === -1)
      ? returns.map(entry => matchReturn(entry, fromId.id, commit.from.fullPath,
        toId.id, commit.to.fullPath, commit.context, point, spatialEnabled, committedAt)).filter(origin => !!origin)
      : []
    const returning = candidates.find(origin => origin.historyPosition === point.position)
      ?? (!spatialEnabled && candidates.length === 1 ? candidates[0] : undefined)
    const startRevision = revision
    const startInput = inputRevision
    let departure: AnchorSnapshot | null = null
    if (spatialEnabled && allowed() && appearance.effectiveMotion.value === 'expressive') {
      // Vue Router calls afterEach synchronously after commitment and before the routed DOM flush.
      const previous = getSurface(!!commit.from.meta.fullPage)
      if (returning?.spatial && sameViewport(returning.spatial.view, readViewport())) departure = targetAnchors(previous, readViewport())?.snapshot ?? null
      else if (!returning && commit.origin) departure = confirmedSource(commit.origin, previous, committedAt)
    }
    const entry = commit.origin
    if (entry) {
      const index = returns.findIndex(value => value.origin.homeId === entry.homeId && value.origin.historyPosition === entry.historyPosition)
      if (index >= 0) returns.splice(index, 1)
      returns.push(rememberEntry(departure ? entry : { ...entry, spatial: undefined }, toId.id, commit.to.fullPath, point, committedAt))
      if (returns.length > 12) returns.shift()
    }
    const deadline = committedAt + 340
    const remaining = () => Math.max(0, deadline - performance.now())
    const token = effects.begin()
    const routeCurrent = () => navigation.isCurrent(commit.token) && router.currentRoute.value.fullPath === commit.to.fullPath && commit.context === contextStamp()
    const current = () => effects.current(token) && routeCurrent()
    await nextTick()
    if (!routeCurrent() || startInput !== inputRevision) return
    if (returning || commit.kind === 'module-to-home') {
      // Native history scroll restoration runs after popstate's microtasks.
      // Restore once on the next frame, without delaying the route's mount.
      await effects.nextFrame(token)
      if (!routeCurrent() || startInput !== inputRevision) return
    }
    const surface = getSurface(!!commit.to.meta.fullPage)
    if (!surface?.isConnected) return
    let returnTrigger: HTMLElement | null = null
    if (returning || commit.kind === 'module-to-home') {
      if (returning) {
        // DOM is committed before restoring; never turn this into smooth scrolling.
        window.scrollTo({ left: returning.scroll[0], top: returning.scroll[1], behavior: 'instant' })
        const main = document.getElementById('app-content')
        if (main) { main.scrollLeft = returning.scroll[2]; main.scrollTop = returning.scroll[3] }
        returnTrigger = findTrigger(returning, surface)
      }
      const focusAnchor = returnTrigger?.querySelector<HTMLElement>('[data-route-entry-icon]') ?? returnTrigger
      const visibleTrigger = focusAnchor && (spatialEnabled ? visibleAnchorRect(focusAnchor, readViewport()) : visibleRect(focusAnchor))
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
      const heading = surface.querySelector<HTMLElement>('h1')
      const focusMain = spatialEnabled ? surface.querySelector<HTMLElement>('[data-rr-motion-focus]') : null
      const headingHidden = !heading?.getClientRects().length || heading.checkVisibility?.({ checkVisibilityCSS: true }) === false
      focusOnce(focusMain && headingHidden ? focusMain : heading ?? surface)
    }
    if (commit.silentRedirect || !allowed() || !current()) return
    if (spatialEnabled) {
      if (startRevision !== revision) return
      const destination = () => returning
        ? sourceAnchors(surface, returning.triggerId, readViewport(), returnTrigger, returning.spatial?.compact)
        : targetAnchors(surface, readViewport())
      await renderer.play({ token, kind: returning ? 'module-to-home' : commit.kind, mode: appearance.effectiveMotion.value,
        committedAt, owner: surface, origin: returning ?? commit.origin, from: departure,
        to: departure ? destination() : null, remeasure: destination })
      return
    }
    if (!remaining()) return
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
    effects.timeout(token, remaining(), cancel)
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
        expectedId: routeVisualIdentity(destination).id, expectedPath: router.resolve(to).fullPath,
        resolvedPath: spatialEnabled ? destination.fullPath : undefined, context: contextStamp(),
      }
      if (spatialEnabled && allowed() && appearance.effectiveMotion.value === 'expressive') {
        const view = readViewport()
        const compact = !!destination.meta.fullPage || view.width < 640
        const source = sourceAnchors(getSurface(!!from.meta.fullPage), origin.triggerId, view, trigger, compact)
        if (source) origin.spatial = { anchors: source.snapshot, captured: performance.now(), revision, view, compact }
      }
      navigation.recordIntent(origin)
      if (allowed() && trigger) {
        const token = effects.begin()
        const frames = spatialEnabled ? [{ opacity: 0.84 }, { opacity: 1 }] : [{ transform: 'scale(0.985)' }, { transform: 'scale(1)' }]
        effects.animate(token, trigger, frames, { duration: 120, easing })
      }
    },
  })
  watch(context, clearContext, { flush: 'sync' })
  // A preference change cancels paint, not a legitimate in-flight navigation.
  watch(appearance.effectiveMotion, interrupt, { flush: 'sync' })
  const inputEvents = ['pointerdown', 'keydown', 'beforeinput', 'wheel', 'touchmove'] as const
  onMounted(() => {
    window.addEventListener('resize', resized)
    if (spatialEnabled) {
      for (const event of inputEvents) document.addEventListener(event, userInput, { capture: true, passive: true })
      window.visualViewport?.addEventListener('resize', visualViewportChanged)
      window.visualViewport?.addEventListener('scroll', visualViewportChanged)
    }
    window.addEventListener('auth-session-boundary-changed', clearContext)
  })
  onBeforeUnmount(() => {
    detach(); effects.dispose(); ghost.value = null; returns.length = 0
    window.removeEventListener('resize', resized)
    if (spatialEnabled) {
      for (const event of inputEvents) document.removeEventListener(event, userInput, true)
      window.visualViewport?.removeEventListener('resize', visualViewportChanged)
      window.visualViewport?.removeEventListener('scroll', visualViewportChanged)
    }
    window.removeEventListener('auth-session-boundary-changed', clearContext)
  })
  return { ghost, spatial: renderer.decoration }
}
