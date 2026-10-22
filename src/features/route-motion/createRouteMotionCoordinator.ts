/** Own only our animations. Base CSS is always the immediately usable state. */
export function createRouteMotionCoordinator() {
  let generation = 0
  let disposed = false
  const releases = new Set<() => void>()
  function cancel() {
    generation++
    const owned = [...releases]
    releases.clear()
    for (const release of owned) release()
  }
  function begin() { cancel(); return generation }
  function current(token: number) { return !disposed && token === generation }
  function own(token: number, release: () => void) {
    if (!current(token)) { release(); return () => {} }
    releases.add(release)
    return () => releases.delete(release)
  }
  function animate(token: number, element: HTMLElement, frames: Keyframe[], options: KeyframeAnimationOptions) {
    if (!current(token) || typeof element.animate !== 'function' || Number(options.duration) <= 0) return
    try {
      const animation = element.animate(frames, { ...options, fill: 'none' })
      const release = () => { try { animation.cancel() } catch { /* Unsupported/finished effect. */ } }
      const disown = own(token, release)
      // Attach rejection handling before cancellation, including synchronous mocks.
      void animation.finished.then(() => { disown(); release() }, () => { disown(); release() })
      return animation
    } catch { /* Animation failure never changes navigation or business state. */ }
  }
  function dispose() { cancel(); disposed = true }
  return { begin, current, own, animate, cancel, dispose }
}
