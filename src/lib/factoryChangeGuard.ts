// Factory buttons update the store before routing. Draft owners must be able
// to veto that update before their keyed workspace is destroyed.
const guards = new Set<() => boolean>()
export function registerFactoryChangeGuard(guard: () => boolean) {
  guards.add(guard)
  return () => { guards.delete(guard) }
}
export function canChangeFactory() {
  return [...guards].every(guard => guard())
}
