/** Own only our animations. Base CSS is always the immediately usable state. */
export function createRouteMotionCoordinator() {
  let generation = 0
  let disposed = false
  const releases = new Set<() => void>()
  function cancel() {
    generation++
    const owned = [...releases]
    releases.clear()
    for (const release of owned) {
      try { release() } catch { /* A broken effect must not strand the rest of this generation. */ }
    }
  }
  function begin() { cancel(); return generation }
  function current(token: number) { return !disposed && token === generation }
  function own(token: number, release: () => void) {
    if (!current(token)) { release(); return () => {} }
    releases.add(release)
    return () => releases.delete(release)
  }
  function finish(token: number) { if (current(token)) cancel() }
  function timeout(token: number, delay: number, callback: () => void) {
    if (!current(token)) return
    const timer = window.setTimeout(() => { disown(); if (current(token)) callback() }, delay)
    const disown = own(token, () => window.clearTimeout(timer))
  }
  function nextFrame(token: number) {
    return new Promise<void>(resolve => {
      if (!current(token) || typeof requestAnimationFrame !== 'function') { resolve(); return }
      const frame = requestAnimationFrame(() => { disown(); resolve() })
      const disown = own(token, () => { cancelAnimationFrame(frame); resolve() })
    })
  }
  function animate(token: number, element: Element, frames: Keyframe[], options: KeyframeAnimationOptions) {
    if (!current(token) || typeof element.animate !== 'function' || Number(options.duration) <= 0) return
    try {
      const animation = element.animate(frames, { ...options, fill: 'none' })
      let released = false
      const release = () => {
        if (released) return
        released = true
        try { animation.cancel() } catch { /* Unsupported/finished effect. */ }
      }
      const disown = own(token, release)
      // Attach rejection handling before cancellation, including synchronous mocks.
      void animation.finished.then(() => { disown(); release() }, () => { disown(); release() })
      return animation
    } catch { /* Animation failure never changes navigation or business state. */ }
  }
  function dispose() { disposed = true; cancel() }
  return { begin, current, own, animate, cancel, finish, timeout, nextFrame, dispose }
}
export type RouteMotionCoordinator = ReturnType<typeof createRouteMotionCoordinator>
