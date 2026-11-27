import { markRaw, type Component, type ObjectDirective } from 'vue'
import { inViewport, sameRect, type MotionRect, type MotionViewport, type SpatialGeometry } from './spatialGeometry'

const source = '[data-rr-motion-source="surface"][data-route-entry-id]'
const target = '[data-rr-motion-target="surface"]'
const nodeKeys = new WeakMap<Element, number>()
const glyphs = new WeakMap<Element, Component>()
// A workspace may supply its existing decorative icon for a flight departing that workspace.
export const vSpatialGlyph: ObjectDirective<HTMLElement, Component> = {
  mounted: (node, binding) => { glyphs.set(node, markRaw(binding.value)) },
  updated: (node, binding) => { if (binding.value !== binding.oldValue) glyphs.set(node, markRaw(binding.value)) },
  unmounted: node => { glyphs.delete(node) },
}
let nextKey = 0

function nodeKey(element: Element) {
  const key = nodeKeys.get(element) ?? ++nextKey
  nodeKeys.set(element, key)
  return key
}

/** Snapshot contains no DOM nodes, text, images or business data. */
export interface IconPaint { ink: string; fill: string }
export interface AnchorSnapshot extends SpatialGeometry { key: number; iconKey: number | null; glyph?: Component; paint?: IconPaint; chrome?: boolean }
export interface SpatialAnchors { element: HTMLElement; iconElement: HTMLElement | null; snapshot: AnchorSnapshot }

export function visibleAnchorRect(element: HTMLElement, view: MotionViewport): MotionRect | null {
  if (!element.isConnected || element.closest('[hidden], [inert]') || !element.getClientRects().length) return null
  if (element.checkVisibility && !element.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) return null
  const { x, y, width, height } = element.getBoundingClientRect()
  const rect = { x, y, width, height }
  if (!inViewport(rect, view)) return null
  for (let node: HTMLElement | null = element; node; node = node.parentElement) {
    const style = getComputedStyle(node)
    if (style.display === 'none' || style.visibility === 'hidden' || style.visibility === 'collapse' || style.opacity === '0') return null
    if (node === element || node === document.body || node === document.documentElement) continue
    const clipX = /auto|scroll|hidden|clip/.test(style.overflowX)
    const clipY = /auto|scroll|hidden|clip/.test(style.overflowY)
    if (!clipX && !clipY) continue
    const box = node.getBoundingClientRect()
    const left = box.left + node.clientLeft, top = box.top + node.clientTop
    if ((clipX && (x < left - 1 || x + width > left + node.clientWidth + 1))
      || (clipY && (y < top - 1 || y + height > top + node.clientHeight + 1))) return null
  }
  return rect
}

function measure(element: HTMLElement, icons: NodeListOf<HTMLElement>, view: MotionViewport): SpatialAnchors | null {
  if (icons.length > 1) return null
  const surface = visibleAnchorRect(element, view)
  if (!surface) return null
  const node = icons[0]
  const icon = node ? visibleAnchorRect(node, view) : null
  if (node && (!icon || !element.contains(node))) return null
  const style = node ? getComputedStyle(node) : null
  const paint = style ? { ink: style.color, fill: style.getPropertyValue('--rr-motion-icon-fill').trim() || style.backgroundColor } : undefined
  return { element, iconElement: node ?? null, snapshot: { surface, icon, key: nodeKey(element), iconKey: node ? nodeKey(node) : null,
    glyph: node ? glyphs.get(node) : undefined, paint, chrome: element.hasAttribute('data-rr-motion-chrome') } }
}

export function sourceAnchors(owner: HTMLElement | null, id: string, view: MotionViewport, trigger?: Element | null, compact = false) {
  if (!owner?.isConnected || !id) return null
  const matches = [...owner.querySelectorAll<HTMLElement>(source)].filter(el => el.dataset.routeEntryId === id)
  const element = matches[0]
  if (matches.length !== 1 || !element || (trigger !== undefined && trigger?.closest(source) !== element)) return null
  const identities = compact ? element.querySelectorAll<HTMLElement>('[data-rr-motion-source="identity"]') : null
  if (identities && identities.length > 1) return null
  return measure(identities?.[0] ?? element, element.querySelectorAll('[data-route-entry-icon]'), view)
}

export function targetAnchors(owner: HTMLElement | null, view: MotionViewport) {
  if (!owner?.isConnected) return null
  const matches = owner.querySelectorAll<HTMLElement>(target)
  const element = matches[0]
  if (matches.length !== 1 || !element || element.matches('table, iframe, canvas, [role="grid"]')) return null
  return measure(element, owner.querySelectorAll('[data-rr-motion-target="icon"]'), view)
}

export function sameAnchors(a: AnchorSnapshot, b: AnchorSnapshot) {
  return a.key === b.key && a.iconKey === b.iconKey && a.glyph === b.glyph && sameRect(a.surface, b.surface) && sameRect(a.icon, b.icon)
}

/** Only a small, declared decoration or plain heading may receive an opacity reveal. */
export function revealAnchor(owner: HTMLElement, view: MotionViewport) {
  const explicit = owner.querySelectorAll<HTMLElement>('[data-rr-motion-target="reveal"]')
  const nodes = explicit.length ? explicit : owner.querySelectorAll<HTMLElement>('h1[data-route-motion-anchor], h2[data-route-motion-anchor]')
  const node = nodes[0]
  if (nodes.length !== 1 || !node || node.matches('button,a,input,select,textarea,iframe,table,[contenteditable]')
    || node.querySelector('button,a,input,select,textarea,iframe,table,[contenteditable]')) return null
  if (!node.matches('h1,h2,[aria-hidden="true"]')) return null
  const rect = visibleAnchorRect(node, view)
  return rect && rect.height <= 120 && rect.width * rect.height <= view.width * view.height * 0.15 ? node : null
}
