export interface PanelPosition { x: number; y: number }
export const defaultPanelHeight = 640
export const panelMargin = 20
export const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value))

export function panelBounds(viewport: { width: number; height: number; top: number; left: number }, width: number, height: number, position: PanelPosition | null | undefined, side: 'left' | 'right') {
  const actualWidth = Math.min(clamp(width, 360, 600), Math.max(0, viewport.width - panelMargin * 2))
  const actualHeight = Math.min(clamp(height, 360, 820), Math.max(0, viewport.height - panelMargin * 2))
  const left = viewport.left + panelMargin, top = viewport.top + panelMargin
  const right = viewport.left + viewport.width - panelMargin, bottom = viewport.top + viewport.height - panelMargin
  return {
    x: clamp(position?.x ?? (side === 'left' ? left : right - actualWidth), left, right - actualWidth),
    y: clamp(position?.y ?? top, top, bottom - actualHeight),
    width: actualWidth, height: actualHeight,
  }
}
