// The host invokes this before changing the global factory context. Component
// update guards run too late: that would clear the old factory's unsaved form.
type Location = {fullPath:string;name?:unknown;path?:string;query?:Record<string,unknown>}
let guard: (() => boolean | Promise<boolean>) | null = null
export function registerSprayNavigationGuard(value: () => boolean | Promise<boolean>) { guard = value; return () => { if (guard === value) guard = null } }
export function sameSprayPageScope(to: Location, from: Location) {
  const clean=(query:Record<string,unknown>)=>JSON.stringify(Object.entries(query).filter(([key])=>!['spray_task','spray_demand','task'].includes(key)).sort(([a],[b])=>a.localeCompare(b)))
  return !!to.path && to.path===from.path && !!to.query && !!from.query && clean(to.query)===clean(from.query)
}
export function guardSprayNavigation(to: Location, from: Location) {
  if (to.fullPath === from.fullPath || to.name === 'login' || to.name === 'change-password') return true
  if (sameSprayPageScope(to,from)) return true
  return guard?.() ?? true
}
