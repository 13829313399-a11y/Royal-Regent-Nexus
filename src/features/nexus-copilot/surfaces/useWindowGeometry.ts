export interface AISurfaceGeometry {
  x: number
  y: number
  width: number
  height: number
}

export const MIN_SURFACE_WIDTH = 360
export const MIN_SURFACE_HEIGHT = 460

export function surfaceBounds() {
  return {
    width: Math.max(window.innerWidth, 320),
    height: Math.max(window.innerHeight, 480),
  }
}

export function clampSurfaceGeometry(input: AISurfaceGeometry): AISurfaceGeometry {
  const viewport = surfaceBounds()
  const maxWidth = Math.max(MIN_SURFACE_WIDTH, Math.min(820, viewport.width * 0.88))
  const maxHeight = Math.max(MIN_SURFACE_HEIGHT, Math.min(900, viewport.height * 0.92))
  const width = Math.min(Math.max(input.width, MIN_SURFACE_WIDTH), maxWidth)
  const height = Math.min(Math.max(input.height, MIN_SURFACE_HEIGHT), maxHeight)
  return {
    x: Math.min(Math.max(input.x, 8), Math.max(8, viewport.width - width - 8)),
    y: Math.min(Math.max(input.y, 8), Math.max(8, viewport.height - height - 8)),
    width,
    height,
  }
}

export function defaultSurfaceGeometry(): AISurfaceGeometry {
  const viewport = surfaceBounds()
  const width = Math.min(440, viewport.width * 0.88)
  const height = Math.min(680, viewport.height * 0.9)
  return clampSurfaceGeometry({
    x: viewport.width - width - 24,
    y: Math.max(16, (viewport.height - height) / 2),
    width,
    height,
  })
}
