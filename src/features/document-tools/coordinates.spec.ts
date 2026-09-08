import { describe, expect, it, vi } from 'vitest'
import {
  mmToPt,
  normalizeCuts,
  parseGroups,
  pointerToVisiblePoint,
  ptToMm,
} from './coordinates'

describe('visible-page PDF coordinates', () => {
  it('uses inverse viewport then visible transform, independent of CSS scaling and crop origin', () => {
    const inverse = vi.fn((x: number, y: number) => [y / 2 + 30, x / 2 + 40])
    const visible = {
      width: 600,
      height: 900,
      convertToPdfPoint: vi.fn(),
      convertToViewportPoint: (x: number, y: number) => [y - 40, x - 30],
    }
    const point = pointerToVisiblePoint(
      250,
      350,
      { left: 100, top: 50, width: 600, height: 900 },
      {
        width: 1200,
        height: 1800,
        convertToPdfPoint: inverse,
        convertToViewportPoint: vi.fn(),
      },
      visible,
    )
    expect(inverse).toHaveBeenCalledWith(300, 600)
    expect(point).toEqual([150, 300])
  })
  it('keeps point precision through millimetres and rejects boundary cuts', () => {
    expect(mmToPt(ptToMm(841.889763))).toBeCloseTo(841.889763, 8)
    expect(normalizeCuts([500, 0, 100, 100, 600, NaN, -1], 600)).toEqual([
      100, 500,
    ])
  })
  it('preserves page order and duplicates for an explicit user decision', () => {
    expect(parseGroups('1-3; 4,6,5; 5', 6)).toEqual([[1, 2, 3], [4, 6, 5], [5]])
    expect(() => parseGroups('0-2', 6)).toThrow()
    expect(() => parseGroups('4-2', 6)).toThrow()
    expect(() => parseGroups('1-7', 6)).toThrow()
  })
})
