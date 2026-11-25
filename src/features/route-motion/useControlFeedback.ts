import { onBeforeUnmount, watch, type Ref } from 'vue'
import type { HomeMotion } from '@/composables/useHomeAppearance'
import { createRouteMotionCoordinator } from './createRouteMotionCoordinator'

/** Confirmed actions and the existing close lifecycle may briefly accent a decorative glyph. */
export function useControlFeedback(mode: Ref<HomeMotion | undefined>) {
  const effects = createRouteMotionCoordinator()
  watch(mode, effects.cancel, { flush: 'sync' })
  onBeforeUnmount(effects.dispose)
  function play(glyph: Element | null, start: Keyframe, duration: number) {
    effects.cancel()
    if (mode.value !== 'expressive' || document.hidden || !glyph?.isConnected || !glyph.getClientRects().length) return
    const token = effects.begin()
    const effect = effects.animate(token, glyph, [start, { transform: 'none', opacity: 1 }], { duration, easing: 'ease-out' })
    if (effect) void effect.finished.then(() => effects.finish(token), () => effects.finish(token))
  }
  function restore(trigger: HTMLElement | null, edge: 'left' | 'right' | 'bottom') {
    const offset = edge === 'bottom' ? '0,3px' : edge === 'right' ? '-3px,0' : '3px,0'
    play(trigger?.querySelector('svg') ?? null, { transform: `translate(${offset})`, opacity: .62 }, 115)
  }
  function confirm(glyph: Element | null) {
    play(glyph, { transform: 'scale(.88)', opacity: .48 }, 170)
  }
  return { restore, confirm }
}
