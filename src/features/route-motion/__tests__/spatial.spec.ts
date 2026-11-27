import { afterEach, describe, expect, it, vi } from 'vitest'
import { Boxes } from '@lucide/vue'
import { createRouteMotionCoordinator } from '../createRouteMotionCoordinator'
import { observeFrameInput } from '../spatialRenderer'
import { spatialProfile } from '../motionProfiles'
import { matchReturn, rememberEntry, type HistoryPoint } from '../returnHistory'
import { revealAnchor, sameAnchors, sourceAnchors, targetAnchors } from '../spatialAnchors'
import { sameRect, sameViewport, surfaceTransform } from '../spatialGeometry'
import type { EntryOrigin } from '../navigation'

const view = { width: 1000, height: 800, dpr: 1, scale: 1 }
const card = { x: 40, y: 220, width: 300, height: 160 }
const head = { x: 90, y: 40, width: 400, height: 80 }
const origin: EntryOrigin = { icon: Boxes, accent: 'teal', soft: 'white', triggerId: 'plan', rect: null,
  viewport: [1000, 800], homeId: 'portal', homePath: '/portal', historyPosition: 4,
  expectedId: 'plan', expectedPath: '/plan', scroll: [0, 200, 0, 0], context: 'scope' }
const forward = { position: 5, current: '/plan', back: '/portal', forward: null }
const back = { position: 4, current: '/portal', back: '/', forward: '/plan' }
afterEach(() => { document.body.replaceChildren(); vi.restoreAllMocks(); vi.useRealTimers(); vi.unstubAllGlobals() })

describe('bounded spatial geometry and confirmed-time budgets', () => {
  it('uses both real rectangles with a top-left origin, including reverse', () => {
    expect(surfaceTransform(card, head, view)).toBe('translate(-50px, 180px) scale(0.75, 2)')
    expect(surfaceTransform(head, card, view)).toBe('translate(50px, -180px) scale(1.3333333333333333, 0.5)')
    expect(sameRect(card, { ...card, x: 40.5 })).toBe(true)
    expect(sameRect(card, { ...card, y: 222 })).toBe(false)
  })
  it.each([{ x: NaN }, { y: Infinity }, { width: 0 }, { x: -1 }, { width: 1200 }, { width: 12 },
    { y: 800 }, { width: 800, height: 500 }])('rejects invalid or unbounded geometry %j', change => {
    expect(surfaceTransform({ ...card, ...change }, head, view)).toBeNull()
  })
  it('rejects zoom, viewport and DPR changes', () => {
    expect(surfaceTransform(card, head, { ...view, scale: 1.5 })).toBeNull()
    expect(surfaceTransform(card, head, { ...view, dpr: 0 })).toBeNull()
    expect(surfaceTransform(card, head, { ...view, height: 300 })).toBeNull()
    expect(surfaceTransform(card, head, { ...view, top: 120 })).toBeNull()
    expect(sameViewport(view, { ...view, top: 40 })).toBe(false)
    expect(sameViewport({ ...view, width: 985, coordinateWidth: 1000 }, view)).toBe(true)
    expect(sameViewport({ ...view, height: 530, coordinateWidth: 1000 }, view)).toBe(false)
    for (const change of [{ width: 999 }, { height: 700 }, { dpr: 2 }, { scale: 2 }]) expect(sameViewport(view, { ...view, ...change })).toBe(false)
  })
  it('honors scene, mode, elapsed time and missing geometry', () => {
    expect(spatialProfile('home-to-module', 'expressive', true, 30)).toEqual({ effect: 'morph', duration: 390 })
    expect(spatialProfile('module-to-home', 'expressive', true, 10).duration).toBe(350)
    expect(spatialProfile('home-to-department', 'expressive', true, 10).duration).toBe(310)
    expect(spatialProfile('module-to-module', 'expressive', true, 10)).toEqual({ effect: 'reveal', duration: 170 })
    expect(spatialProfile('home-to-module', 'calm', true, 20)).toEqual({ effect: 'reveal', duration: 120 })
    expect(spatialProfile('home-to-module', 'expressive', false, 0).effect).toBe('reveal')
    for (const wait of [120, 500, NaN, Infinity, -1]) expect(spatialProfile('home-to-module', 'expressive', true, wait).effect).toBe('instant')
    expect(spatialProfile('home-to-module', 'off', true, 0).effect).toBe('instant')
    expect(spatialProfile('none', 'expressive', true, 0).effect).toBe('instant')
  })
})

function fixture() {
  document.body.innerHTML = '<main><article data-route-entry-id="plan" data-rr-motion-source="surface"><span data-route-entry-icon></span></article><header data-rr-motion-target="surface"><i data-rr-motion-target="icon"></i></header><h1 data-route-motion-anchor>Title</h1></main>'
  vi.spyOn(HTMLElement.prototype, 'getClientRects').mockReturnValue([{}] as unknown as DOMRectList)
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ ...head, left: head.x, top: head.y,
    right: head.x + head.width, bottom: head.y + head.height, toJSON: () => head })
  return document.querySelector('main')!
}
describe('unique scoped presentation anchors', () => {
  it('requires the exact activated element and connected owner, and detects node replacement at equal coordinates', () => {
    const owner = fixture(), article = owner.querySelector('article')!
    expect(sourceAnchors(owner, 'other', view)).toBeNull()
    expect(sourceAnchors(owner, 'plan', view, owner)).toBeNull()
    const before = sourceAnchors(owner, 'plan', view, article.firstElementChild)!.snapshot
    expect(sameAnchors(before, sourceAnchors(owner, 'plan', view)!.snapshot)).toBe(true)
    article.replaceWith(article.cloneNode(true))
    expect(sameAnchors(before, sourceAnchors(owner, 'plan', view)!.snapshot)).toBe(false)
    owner.remove()
    expect(targetAnchors(owner, view)).toBeNull()
  })
  it('uses the exact declared card identity for a compact workspace, including on return', () => {
    const owner = fixture(), card = owner.querySelector('article')!, icon = card.firstElementChild!
    const identity = document.createElement('div')
    identity.dataset.rrMotionSource = 'identity'; card.append(identity); identity.append(icon)
    expect(sourceAnchors(owner, 'plan', view, card)?.element).toBe(card)
    const capture = sourceAnchors(owner, 'plan', view, card, true)!
    expect(capture.element).toBe(identity)
    expect(sameAnchors(capture.snapshot, sourceAnchors(owner, 'plan', view, undefined, true)!.snapshot)).toBe(true)
    card.append(identity.cloneNode(true))
    expect(sourceAnchors(owner, 'plan', view, card, true)).toBeNull()
  })
  it('rejects ambiguous, hidden, clipped, misplaced or missing anchors', () => {
    const owner = fixture(), el = owner.querySelector('header')!, icon = el.firstElementChild!
    owner.append(el.cloneNode(true)); expect(targetAnchors(owner, view)).toBeNull(); owner.lastChild!.remove()
    el.hidden = true; expect(targetAnchors(owner, view)).toBeNull(); el.hidden = false
    owner.setAttribute('inert', ''); expect(targetAnchors(owner, view)).toBeNull(); owner.removeAttribute('inert')
    owner.style.overflowX = 'hidden'; expect(targetAnchors(owner, view)).toBeNull(); owner.style.overflowX = ''
    owner.append(icon); expect(targetAnchors(owner, view)).toBeNull()
    icon.remove(); expect(targetAnchors(owner, view)?.snapshot.icon).toBeNull()
    owner.append(owner.querySelector('article')!.cloneNode(true)); expect(sourceAnchors(owner, 'plan', view)).toBeNull()
    el.remove(); expect(targetAnchors(owner, view)).toBeNull()
  })
  it('restricts fallback to one safe heading or decoration', () => {
    const owner = fixture(), h1 = owner.querySelector('h1')!
    expect(revealAnchor(owner, view)).toBe(h1)
    h1.append(document.createElement('button')); expect(revealAnchor(owner, view)).toBeNull()
    const element = document.createElement('span'); element.dataset.rrMotionTarget = 'reveal'; owner.append(element)
    expect(revealAnchor(owner, view)).toBeNull()
    element.setAttribute('aria-hidden', 'true'); expect(revealAnchor(owner, view)).toBe(element)
    owner.append(element.cloneNode(true)); expect(revealAnchor(owner, view)).toBeNull()
  })
})
describe('verified native return edges', () => {
  const record = rememberEntry(origin, 'plan', '/plan', forward, 200)
  const match = (home: HistoryPoint = back, from = '/plan', scope = 'scope', now = 350) =>
    matchReturn(record, 'plan', from, 'portal', '/portal', scope, home, true, now)
  it('matches only the adjacent direct pair in the original scope and lifetime', () => {
    expect(match()).toBe(origin)
    for (const change of [{ position: null }, { position: 6 }, { current: '/other' }, { forward: '/other' }]) expect(match({ ...back, ...change })).toBeUndefined()
    expect(match(back, '/plan#row')).toBeUndefined()
    expect(match(back, '/plan', 'other')).toBeUndefined()
    expect(match(back, '/plan', 'scope', 201 + 30 * 60_000)).toBeUndefined()
    expect(match(back, '/plan', 'scope', 100)).toBeUndefined()
    expect(matchReturn(record, 'plan', '/plan', 'portal', '/portal', 'scope', back, false, 201 + 60 * 60_000)).toBe(origin)
    expect(matchReturn(record, 'another', '/plan', 'portal', '/portal', 'scope', back, true, 350)).toBeUndefined()
    expect(matchReturn(rememberEntry(origin, 'plan', '/plan', { ...forward, position: 8 }, 200),
      'plan', '/plan', 'portal', '/portal', 'scope', back, true, 350)).toBeUndefined()
  })
})
describe('input across workspace documents', () => {
  it('interrupts from a loaded frame and releases the child listeners with the flight', () => {
    const host = document.createElement('main'), frame = document.createElement('iframe')
    document.body.append(host)
    const stop = vi.fn(), detach = observeFrameInput(host, stop)
    host.append(frame)
    frame.dispatchEvent(new Event('load'))
    const child = frame.contentDocument!
    child.dispatchEvent(new Event('beforeinput', { bubbles: true }))
    expect(stop).toHaveBeenCalledOnce()
    detach()
    child.dispatchEvent(new Event('keydown', { bubbles: true }))
    expect(stop).toHaveBeenCalledOnce()
    host.remove()
  })
})

describe('generation-owned cleanup', () => {
  it('settles a cancelled frame, clears timers and tolerates a broken release and stale finish', async () => {
    vi.useFakeTimers(); const effects = createRouteMotionCoordinator(), first = effects.begin()
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => window.setTimeout(() => cb(0), 16))
    vi.stubGlobal('cancelAnimationFrame', (id: number) => window.clearTimeout(id))
    const timer = vi.fn(), nextRelease = vi.fn(), release = vi.fn()
    effects.own(first, () => { throw Error('broken effect') }); effects.own(first, release)
    const pendingFrame = effects.nextFrame(first)
    effects.timeout(first, 50, timer)
    const second = effects.begin(); effects.own(second, nextRelease)
    await pendingFrame; effects.finish(first); vi.advanceTimersByTime(60)
    expect(timer).not.toHaveBeenCalled(); expect(release).toHaveBeenCalledOnce(); expect(nextRelease).not.toHaveBeenCalled()
    effects.dispose(); expect(nextRelease).toHaveBeenCalledOnce(); expect(vi.getTimerCount()).toBe(0)
  })
})
