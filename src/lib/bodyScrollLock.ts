export type BodyScrollLockRelease = () => void

const activeLocks = new Set<symbol>()
let overflowBeforeFirstLock: string | null = null

export function acquireBodyScrollLock(): BodyScrollLockRelease {
  if (typeof document === 'undefined') return () => undefined

  const token = Symbol('body-scroll-lock')
  if (activeLocks.size === 0) {
    overflowBeforeFirstLock = document.body.style.overflow
    document.body.style.overflow = 'hidden'
  }
  activeLocks.add(token)

  let released = false
  return () => {
    if (released) return
    released = true
    activeLocks.delete(token)
    if (activeLocks.size === 0) {
      document.body.style.overflow = overflowBeforeFirstLock ?? ''
      overflowBeforeFirstLock = null
    }
  }
}
