import { nextTick, shallowRef, type Component } from 'vue'
import type { HomeMotion } from '@/composables/useHomeAppearance'
import type { MotionKind } from './classifyNavigation'
import type { RouteMotionCoordinator } from './createRouteMotionCoordinator'
import { spatialProfile } from './motionProfiles'
import type { EntryOrigin } from './navigation'
import { revealAnchor, sameAnchors, type AnchorSnapshot, type IconPaint, type SpatialAnchors } from './spatialAnchors'
import { readViewport, sameViewport, surfaceTransform, type MotionRect } from './spatialGeometry'

interface IconFlight { x: number; y: number; size: number; frames: Keyframe[] }
export interface SpatialDecoration {
  token: number
  surface: MotionRect
  badge: IconFlight | null
  icon: Component
  accent: string
  soft: string
  chrome?: boolean
  clip?: string
}
interface RenderRequest {
  token: number
  kind: MotionKind
  mode: HomeMotion
  committedAt: number
  owner: HTMLElement
  origin?: EntryOrigin | null
  from: AnchorSnapshot | null
  to: SpatialAnchors | null
  remeasure: () => SpatialAnchors | null
}

function iconFlight(from: MotionRect | null, to: MotionRect | null, returning: boolean,
  startPaint?: IconPaint, endPaint?: IconPaint): IconFlight | null {
  if (!from || !to) return null
  const size = Math.min(to.width, to.height, 64)
  const x = to.x + (to.width - size) / 2, y = to.y + (to.height - size) / 2
  const dx = from.x + from.width / 2 - (x + size / 2), dy = from.y + from.height / 2 - (y + size / 2)
  const scale = Math.min(from.width, from.height, 64) / size
  // Approach the header icon from the card's side of the title, then settle vertically.
  // Reversing the same control point retraces the path out of the header.
  const bendX = returning ? dx : 0
  const cardY = returning ? 0 : dy
  const bendY = cardY + Math.sign(returning ? -dy : dy) * Math.min(44, Math.abs(dx) * 0.12)
  const frames = [0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.82, 1].map(offset => {
    // Complete positioning before crossfading two glyphs. Even one moving duplicate reads as a second icon.
    const t = Math.min(1, offset / 0.75), left = 1 - t
    const tx = left * left * dx + 2 * left * t * bendX, ty = left * left * dy + 2 * left * t * bendY
    // Once docked, the real icon container supplies the background, including gradient or dark finishes.
    const paint = offset === 0 ? { color: startPaint?.ink, backgroundColor: startPaint?.fill }
      : offset >= 0.75 ? { color: endPaint?.ink, backgroundColor: 'transparent' } : {}
    return { offset, ...paint, transform: `translate(${tx}px, ${ty}px) scale(${left * scale + t})`,
      opacity: offset <= 0.82 ? 1 : (1 - offset) / 0.18 }
  })
  return { x, y, size, frames }
}

function materialFrames(from: MotionRect, to: MotionRect, start: string): Keyframe[] {
  const sx = from.width / to.width, sy = from.height / to.height
  const edge = 'color-mix(in srgb, var(--rr-flight-accent) 34%, transparent)'
  return [0, 0.25, 0.5, 0.75, 1].map(t => {
    const w = sx + (1 - sx) * t, h = sy + (1 - sy) * t
    // Compensate in the layer's local coordinates so the visible stroke and corners stay uniform.
    const shadow = [[1 / w, 0], [-1 / w, 0], [0, 1 / h], [0, -1 / h]]
      .map(([x, y]) => `inset ${x}px ${y}px 0 ${edge}`).join(', ')
    return { offset: t, ...(t === 0 ? { transform: start } : t === 1 ? { transform: 'none' } : {}),
      borderRadius: `${16 / w}px / ${16 / h}px`, boxShadow: shadow, opacity: (1 - t) * 0.92 }
  })
}

function decorativeGlyph(anchor: HTMLElement | null) {
  const glyph = anchor?.firstElementChild
  return anchor?.childElementCount === 1 && glyph instanceof SVGElement && glyph.tagName.toLowerCase() === 'svg'
    && (anchor.getAttribute('aria-hidden') === 'true' || glyph.getAttribute('aria-hidden') === 'true')
    && !anchor.matches('button,a,[tabindex],[contenteditable]') && !glyph.querySelector('a,[tabindex],foreignObject')
    ? glyph : null
}

function titleClip(target: HTMLElement, returning: boolean) {
  // The body portal sits outside the app shell's isolated stacking context.
  const bar = returning ? target.closest('.app-shell')?.querySelector('[data-rr-motion-topbar]') : null
  const barRect = bar?.getBoundingClientRect()
  const edge = barRect && barRect.top <= 1 ? Math.max(0, barRect.bottom) : 0
  const chromeClip = edge ? `inset(${edge}px 0 0)` : undefined
  const title = target.querySelector('[data-rr-motion-label],h1,h2,h3')
  if (!title) return chromeClip
  const { left, top, right, bottom, width, height } = title.getBoundingClientRect()
  if (!width || !height || height > 120 || top < edge + 3) return chromeClip
  const x = left - 3, y = top - 3, r = right + 3, b = bottom + 3
  return `polygon(evenodd, 0 ${edge}px, 100% ${edge}px, 100% 100%, 0 100%, 0 ${edge}px, ${x}px ${y}px, ${x}px ${b}px, ${r}px ${b}px, ${r}px ${y}px, ${x}px ${y}px)`
}

function easingFor(owner: HTMLElement) {
  const spring = getComputedStyle(owner).getPropertyValue('--motion-ease-spring-smooth').trim()
  return spring && globalThis.CSS?.supports('animation-timing-function', spring) ? spring : 'cubic-bezier(0.16, 1, 0.3, 1)'
}

// Input in an embedded document never reaches the host document's capture listeners.
export function observeFrameInput(host: HTMLElement, interrupt: () => void) {
  const documents = new Set<Document>()
  const inputs = ['pointerdown', 'keydown', 'beforeinput', 'wheel', 'touchmove']
  const options = { capture: true, passive: true }
  function connect(frame: HTMLIFrameElement) {
    const doc = frame.contentDocument
    if (!doc || documents.has(doc)) return
    documents.add(doc)
    for (const name of inputs) doc.addEventListener(name, interrupt, options)
  }
  for (const frame of host.querySelectorAll('iframe')) connect(frame)
  const loaded = (event: Event) => {
    if (event.target instanceof HTMLIFrameElement) connect(event.target)
  }
  host.addEventListener('load', loaded, options)
  // Also relinquish paint when focus moves to an opaque or newly navigating frame.
  window.addEventListener('blur', interrupt)
  return () => {
    host.removeEventListener('load', loaded, true)
    window.removeEventListener('blur', interrupt)
    for (const doc of documents) for (const name of inputs) doc.removeEventListener(name, interrupt, true)
    documents.clear()
  }
}

export function createSpatialRenderer(effects: RouteMotionCoordinator, getLayer: () => HTMLElement | null) {
  const decoration = shallowRef<SpatialDecoration | null>(null)

  async function play(request: RenderRequest) {
    const { token, owner, from, origin } = request
    let to = request.to
    if (!effects.current(token) || !owner.isConnected || typeof owner.animate !== 'function') return
    const view = readViewport()
    let transform = from && to && origin ? surfaceTransform(from.surface, to.snapshot.surface, view) : null
    const elapsed = performance.now() - request.committedAt
    const profile = spatialProfile(request.kind, request.mode, !!transform, elapsed)
    if (profile.effect === 'instant') return
    const finish = () => effects.finish(token)
    const deadline = request.committedAt + elapsed + profile.duration
    if (profile.effect === 'reveal') {
      const heading = revealAnchor(owner, view)
      const duration = deadline - performance.now()
      if (heading && duration >= 48) {
        const frameHost = heading.closest<HTMLElement>('[data-rr-motion-frame-host]')
        if (frameHost) effects.own(token, observeFrameInput(frameHost, finish))
        effects.animate(token, heading, [{ opacity: 0.78 }, { opacity: 1 }], { duration, easing: 'ease-out' })
        effects.timeout(token, duration, finish)
      }
      return
    }
    if (!transform || !from || !to || !origin) return
    // Restoring native scroll can put the stationary pointer over the returning card.
    // Its hover transforms must not move the destination while the glyph is docking.
    const returnCard = request.kind === 'module-to-home' ? to.element.closest<HTMLElement>('.portal-module-card[data-rr-motion-source="surface"]') : null
    if (returnCard) {
      returnCard.setAttribute('data-rr-motion-docking', '')
      effects.own(token, () => returnCard.removeAttribute('data-rr-motion-docking'))
      const stable = request.remeasure()
      if (!stable || stable.element !== to.element || stable.iconElement !== to.iconElement) { finish(); return }
      to = stable
      transform = surfaceTransform(from.surface, to.snapshot.surface, view)
      if (!transform) { finish(); return }
    }
    const ease = easingFor(owner)
    const glyph = decorativeGlyph(to.iconElement)
    const badge = glyph ? iconFlight(from.icon, to.snapshot.icon, request.kind === 'module-to-home', from.paint, to.snapshot.paint) : null
    const frames = materialFrames(from.surface, to.snapshot.surface, transform)
    decoration.value = { token, surface: to.snapshot.surface, badge, chrome: to.snapshot.chrome, clip: titleClip(to.element, request.kind === 'module-to-home'),
      icon: from.glyph ?? origin.icon, accent: origin.accent, soft: origin.soft }
    effects.own(token, () => { if (decoration.value?.token === token) decoration.value = null })
    await nextTick()
    if (!effects.current(token)) return
    const layer = getLayer()
    const plane = layer?.querySelector<HTMLElement>('.rr-spatial-plane')
    const duration = deadline - performance.now()
    if (!plane || layer?.dataset.rrSpatialLayer !== String(token) || duration < 48) { finish(); return }

    const frameHost = to.element.closest<HTMLElement>('[data-rr-motion-frame-host]')
    if (frameHost) effects.own(token, observeFrameInput(frameHost, finish))

    const verify = () => {
      if (!effects.current(token)) return
      const live = request.remeasure()
      if (!owner.isConnected || !sameViewport(view, readViewport()) || !live || !sameAnchors(to.snapshot, live.snapshot)) finish()
    }
    verify()
    if (!effects.current(token)) return
    // Geometry is immutable during a flight. Recheck only on layout-affecting events.
    document.addEventListener('scroll', verify, { passive: true, capture: true })
    effects.own(token, () => document.removeEventListener('scroll', verify, true))
    if (typeof ResizeObserver === 'function') {
      const sizes = new ResizeObserver(verify)
      sizes.observe(to.element)
      effects.own(token, () => sizes.disconnect())
    }
    // A sibling or an outer shell can move the header without resizing it.
    // Let the browser notify us when it crosses its initial viewport rectangle.
    if (typeof IntersectionObserver === 'function') {
      const { x, y, width, height } = to.snapshot.surface
      const margin = [y, document.documentElement.clientWidth - x - width, document.documentElement.clientHeight - y - height, x]
        .map(distance => -Math.max(0, Math.floor(distance) - 1) + 'px').join(' ')
      const position = new IntersectionObserver(verify, { rootMargin: margin, threshold: 1 })
      position.observe(to.element)
      effects.own(token, () => position.disconnect())
    }
    if (typeof MutationObserver === 'function') {
      const declarations = '[data-rr-motion-source],[data-rr-motion-target],[data-route-entry-icon]'
      const icon = to.iconElement
      const attributes = ['hidden', 'inert', 'class', 'style', 'data-route-entry-id', 'data-rr-motion-source', 'data-rr-motion-target', 'data-route-entry-icon']
      const anchors = new MutationObserver(records => {
        if (!owner.isConnected || !to.element.isConnected) { finish(); return }
        const changed = records.some(record => record.type === 'attributes'
          ? record.attributeName?.startsWith('data-') || record.target.contains(to.element) || (icon && record.target.contains(icon))
          : [...record.addedNodes, ...record.removedNodes].some(node => node instanceof Element
              && (node.matches(declarations) || node.querySelector(declarations))))
        if (changed) verify()
      })
      anchors.observe(owner, { subtree: true, childList: true, attributes: true, attributeFilter: attributes })
      for (let ancestor = owner.parentElement; ancestor; ancestor = ancestor.parentElement) {
        anchors.observe(ancestor, { childList: true, attributes: true, attributeFilter: attributes })
      }
      effects.own(token, () => anchors.disconnect())
    }
    const flightDuration = deadline - performance.now()
    if (flightDuration < 48) { finish(); return }
    const flight = effects.animate(token, plane, frames, { duration: flightDuration, easing: ease })
    if (!flight) { finish(); return }
    const icon = layer.querySelector<HTMLElement>('.rr-spatial-icon')
    if (icon && badge && glyph) {
      const moving = effects.animate(token, icon, badge.frames, { duration: flightDuration, easing: ease })
      if (moving) effects.animate(token, glyph, [{ opacity: 0 }, { offset: 0.82, opacity: 0 }, { opacity: 1 }],
        { duration: flightDuration, easing: ease })
    }
    effects.timeout(token, Math.max(0, deadline - performance.now()), finish)
    void flight.finished.then(finish, finish)
  }
  return { decoration, play }
}
