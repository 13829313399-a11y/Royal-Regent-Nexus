export interface ViewportTransform {
  width: number
  height: number
  convertToPdfPoint(x: number, y: number): number[]
  convertToViewportPoint(x: number, y: number): number[]
}
/** Use PDF.js inverse transform, then the unscaled rotated viewport. Both describe the visible CropBox. */
export function pointerToVisiblePoint(
  clientX: number,
  clientY: number,
  rect: { left: number; top: number; width: number; height: number },
  viewport: ViewportTransform,
  visible: ViewportTransform,
): [number, number] {
  const pixelX = ((clientX - rect.left) * viewport.width) / rect.width
  const pixelY = ((clientY - rect.top) * viewport.height) / rect.height
  const native = viewport.convertToPdfPoint(pixelX, pixelY)
  const point = visible.convertToViewportPoint(native[0]!, native[1]!)
  return [
    Math.max(0, Math.min(visible.width, point[0]!)),
    Math.max(0, Math.min(visible.height, point[1]!)),
  ]
}
export const mmToPt = (value: number) => (value * 72) / 25.4
export const ptToMm = (value: number) => (value * 25.4) / 72
export function normalizeCuts(cuts: number[], extent: number) {
  return [
    ...new Set(
      cuts.filter(
        (value) => Number.isFinite(value) && value > 0 && value < extent,
      ),
    ),
  ].sort((a, b) => a - b)
}
export function parseGroups(input: string, pages: number): number[][] {
  if (!input.trim()) return []
  return input.split(';').map((group) =>
    group.split(',').flatMap((token) => {
      const match = token.trim().match(/^(\d+)(?:\s*-\s*(\d+))?$/)
      if (!match) throw new Error('分组格式应为 1-3;4,6,5')
      const start = Number(match[1]),
        end = Number(match[2] ?? match[1])
      if (start < 1 || end < start || end > pages)
        throw new Error(`页码需在 1–${pages} 之间，区间终点不能小于起点`)
      return Array.from(
        { length: end - start + 1 },
        (_, index) => start + index,
      )
    }),
  )
}
