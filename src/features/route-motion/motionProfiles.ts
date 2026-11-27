import type { HomeMotion } from '@/composables/useHomeAppearance'
import type { MotionKind } from './classifyNavigation'

export type SpatialMotionProfile = { effect: 'instant' | 'reveal' | 'morph'; duration: number }

export function spatialProfile(kind: MotionKind, mode: HomeMotion, hasGeometry: boolean, elapsed: number): SpatialMotionProfile {
  if (kind === 'none' || mode === 'off' || !Number.isFinite(elapsed) || elapsed < 0) return { effect: 'instant', duration: 0 }
  const morph = mode === 'expressive' && hasGeometry && kind !== 'module-to-module' && elapsed < 120
  let budget = 140
  if (morph) budget = kind === 'module-to-home' ? 360 : kind === 'home-to-department' ? 320 : 420
  else if (mode === 'expressive' && kind === 'module-to-module') budget = 180
  const duration = budget - elapsed
  if (duration < 48) return { effect: 'instant', duration: 0 }
  return { effect: morph ? 'morph' : 'reveal', duration }
}
