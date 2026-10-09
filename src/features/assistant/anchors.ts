import { nextTick } from 'vue'
export interface AssistantHelpTarget { helpId: string; element: () => HTMLElement | null; reveal?: () => Promise<void> }
const registered = new Map<string, AssistantHelpTarget>()
export function registerAssistantTarget(target: AssistantHelpTarget) {
  registered.set(target.helpId, target)
  return () => { if (registered.get(target.helpId) === target) registered.delete(target.helpId) }
}
function visible(element: HTMLElement) { return !!element.getClientRects().length && !element.closest('[inert], [aria-hidden="true"]') }
export function currentTargets() {
  const result = new Map<string, HTMLElement>()
  document.querySelectorAll<HTMLElement>('[data-yl-help]').forEach(el => { const id = el.dataset.ylHelp; if (id && visible(el) && !result.has(id)) result.set(id, el) })
  for (const [id, target] of registered) { const element = target.element(); if (element && visible(element)) result.set(id, element) }
  return result
}
export function availableTargetIds() {
  // The assistant's own mobile dialog makes the page inert temporarily. Listing
  // semantic IDs must still work; revealTarget rechecks visibility after closing it.
  const ids = [...document.querySelectorAll<HTMLElement>('[data-yl-help]')]
    .filter(el => !!el.getClientRects().length && !el.closest('[aria-hidden="true"]'))
    .map(el => el.dataset.ylHelp!)
  return [...new Set([...ids, ...registered.keys()])]
}
export async function revealTarget(id: string) {
  await registered.get(id)?.reveal?.()
  await nextTick()
  const element = currentTargets().get(id)
  if (!element || !element.isConnected) throw new Error('当前页面没有可见的目标；请先打开相应页签，或核对可用权限。')
  element.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'center', inline: 'nearest' })
  return element
}
