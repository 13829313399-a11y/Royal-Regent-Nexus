import { onBeforeUnmount, watch, type Component, type Ref, h, render } from 'vue'
import type { HomeMotion } from '@/composables/useHomeAppearance'
import { createRouteMotionCoordinator } from './createRouteMotionCoordinator'
import { visibleAnchorRect } from './spatialAnchors'
import { readViewport, sameRect, sameViewport } from './spatialGeometry'

/** A single decorative glyph joins a real list item and its admitted detail. */
export function useDetailMotion(mode: Ref<HomeMotion | undefined>, context: () => string) {
  const effects = createRouteMotionCoordinator()
  type Origin = { id: string; node: HTMLElement; icon: Component }
  let linked: Origin | null = null
  let returningId: string | null = null
  let pending: { origin: Origin; dock: (target: HTMLElement) => void } | null = null

  function clear() { effects.cancel(); pending = null; linked = null }
  watch([mode, context], clear, { flush: 'sync' })
  onBeforeUnmount(() => { clear(); effects.dispose() })

  function prepare(origin: Origin, from: HTMLElement, returning = false) {
    effects.cancel()
    if (mode.value !== 'expressive' || document.hidden || typeof from.animate !== 'function') return
    const view = readViewport(), start = visibleAnchorRect(from, view)
    if (!start || start.width > 72 || start.height > 72) return
    const token = effects.begin(), started = performance.now()
    const stop = () => effects.finish(token)
    const lease = new AbortController()
    const listen = { capture: true, passive: true, signal: lease.signal }
    for (const name of ['pointerdown', 'keydown', 'beforeinput', 'wheel', 'scroll', 'touchmove']) document.addEventListener(name, stop, listen)
    window.addEventListener('resize', stop, listen)
    window.addEventListener('blur', stop, { signal: lease.signal })
    returningId = returning ? origin.id : null
    effects.own(token, () => { lease.abort(); pending = null; returningId = null })
    effects.timeout(token, 680, stop)
    pending = { origin, dock(target) {
      pending = null
      const end = visibleAnchorRect(target, view)
      const duration = Math.min(returning ? 175 : 215, 680 - (performance.now() - started))
      if (!end || end.width > 72 || end.height > 72 || duration < 110
        || !sameViewport(view, readViewport()) || !sameRect(start, visibleAnchorRect(from, view))) { stop(); return }
      const dx = start.x + start.width / 2 - end.x - end.width / 2
      const dy = start.y + start.height / 2 - end.y - end.height / 2
      if (Math.hypot(dx, dy) > Math.hypot(view.width, view.height) * 0.72) { stop(); return }
      const layer = document.createElement('span'), paint = getComputedStyle(from)
      layer.className = 'rr-detail-glyph'
      layer.setAttribute('aria-hidden', 'true')
      layer.inert = true
      Object.assign(layer.style, { left: end.x + 'px', top: end.y + 'px', width: end.width + 'px',
        height: end.height + 'px', color: paint.color, backgroundColor: paint.backgroundColor })
      render(h(origin.icon, { size: 17, 'aria-hidden': 'true' }), layer)
      document.body.append(layer)
      effects.own(token, () => { render(null, layer); layer.remove() })
      const timing = { duration, easing: 'cubic-bezier(.2,.75,.2,1)' }
      const flight = effects.animate(token, layer, [
        { transform: `translate(${dx}px, ${dy}px)`, opacity: 0.92 },
        { transform: 'none', opacity: 1, offset: 0.72 },
        { transform: 'none', opacity: 1, offset: 0.86 },
        { transform: 'none', opacity: 0 },
      ], timing)
      if (!flight) { stop(); return }
      if (!returning) linked = origin
      const tree = target.closest('main') ?? target.getRootNode()
      if (typeof MutationObserver === 'function') {
        const removal = new MutationObserver(() => { if (!target.isConnected) stop() })
        removal.observe(tree, { subtree: true, childList: true })
        effects.own(token, () => removal.disconnect())
      }
      const verify = () => {
        if (!target.isConnected || !sameRect(end, visibleAnchorRect(target, readViewport()))) stop()
      }
      if (typeof ResizeObserver === 'function') {
        const size = new ResizeObserver(verify)
        size.observe(target)
        effects.own(token, () => size.disconnect())
      }
      if (typeof IntersectionObserver === 'function') {
        const margin = [end.y, view.width - end.x - end.width, view.height - end.y - end.height, end.x]
          .map(value => -Math.max(0, Math.floor(value) - 1) + 'px').join(' ')
        const position = new IntersectionObserver(verify, { rootMargin: margin, threshold: 1 })
        position.observe(target)
        effects.own(token, () => position.disconnect())
      }
      const glyph = target.querySelector('svg')
      if (glyph) effects.animate(token, glyph, [{ opacity: 0 }, { opacity: 0, offset: 0.72 },
        { opacity: 1, offset: 0.86 }, { opacity: 1 }], timing)
      void flight.finished.then(stop, stop)
    } }
  }

  function select(id: string, source: HTMLElement, icon: Component) {
    linked = null
    prepare({ id, node: source, icon }, source)
  }
  function arrive(id: string, target: HTMLElement | null) {
    if (pending?.origin.id === id && target) pending.dock(target)
  }
  function depart(id: string, source: HTMLElement | null) {
    const origin = linked
    clear()
    if (!source || !origin || origin.id !== id || !origin.node.isConnected) return
    prepare(origin, source, true)
    pending?.dock(origin.node)
  }
  function invalidate(id: string) {
    if (returningId !== id && (linked?.id === id || pending?.origin.id === id)) clear()
  }
  return { select, arrive, depart, clear, invalidate }
}
