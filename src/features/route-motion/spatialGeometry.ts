export interface MotionRect { x: number; y: number; width: number; height: number }
export interface MotionViewport {
  width: number; height: number; dpr: number; scale: number; left?: number; top?: number
  // A document scrollbar changes the visible bounds without changing the coordinate system.
  coordinateWidth?: number; coordinateHeight?: number
}
export interface SpatialGeometry { surface: MotionRect; icon: MotionRect | null }

export function readViewport(): MotionViewport {
  const visible = window.visualViewport
  const width = visible?.width ?? innerWidth, height = visible?.height ?? innerHeight
  const doc = document.documentElement
  return { width, height, coordinateWidth: Math.abs(width - doc.clientWidth) < 1 ? innerWidth : width,
    coordinateHeight: Math.abs(height - doc.clientHeight) < 1 ? innerHeight : height,
    left: visible?.offsetLeft ?? 0, top: visible?.offsetTop ?? 0, dpr: window.devicePixelRatio, scale: visible?.scale ?? 1 }
}

export function sameViewport(a: MotionViewport, b: MotionViewport) {
  return (a.coordinateWidth ?? a.width) === (b.coordinateWidth ?? b.width)
    && (a.coordinateHeight ?? a.height) === (b.coordinateHeight ?? b.height) && a.dpr === b.dpr && a.scale === b.scale
    && (a.left ?? 0) === (b.left ?? 0) && (a.top ?? 0) === (b.top ?? 0)
}

export function inViewport(rect: MotionRect, view: MotionViewport) {
  const { x, y, width, height } = rect
  const left = view.left ?? 0, top = view.top ?? 0
  return [x, y, width, height, view.width, view.height, view.dpr, left, top].every(Number.isFinite)
    && view.dpr > 0 && view.scale === 1 && width > 0 && height > 0 && x >= left && y >= top
    && x + width <= left + view.width && y + height <= top + view.height
}

export function sameRect(a: MotionRect | null, b: MotionRect | null) {
  if (!a || !b) return a === b
  return Math.abs(a.x - b.x) < 1 && Math.abs(a.y - b.y) < 1
    && Math.abs(a.width - b.width) < 1 && Math.abs(a.height - b.height) < 1
}

export function surfaceTransform(from: MotionRect, to: MotionRect, view: MotionViewport): string | null {
  if (![from, to].every(r => inViewport(r, view) && r.width >= 12 && r.height >= 12
      && r.width * r.height <= view.width * view.height * 0.35)) return null
  const sx = from.width / to.width, sy = from.height / to.height
  const dx = from.x - to.x, dy = from.y - to.y
  if (Math.max(sx, sy, 1 / sx, 1 / sy) > 8 || Math.hypot(dx, dy) > Math.hypot(view.width, view.height) * 0.8) return null
  return `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})`
}
