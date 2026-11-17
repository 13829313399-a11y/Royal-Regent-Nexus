import { describe, expect, it, vi } from 'vitest'
import {
  mmToPt,
  normalizeCuts,
  normalizeGroupSeparators,
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

describe('PDF output groups', () => {
  it('normalizes only separators for compatibility with existing workers', () => {
    expect(normalizeGroupSeparators('1-10； 11-20；21，23,22;31-42')).toBe(
      '1-10; 11-20;21,23,22;31-42',
    )
  })

  it('accepts Chinese and mixed separators without changing page order or duplicates', () => {
    expect(parseGroups('1-3； 4，6,5; 5', 6)).toEqual([
      [1, 2, 3], [4, 6, 5], [5],
    ])
  })

  it('splits the reported 42-page selection into four complete groups', () => {
    expect(parseGroups('1-10；11-20；21-30；31-42', 42)).toEqual([
      [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
      [11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
      [21, 22, 23, 24, 25, 26, 27, 28, 29, 30],
      [31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42],
    ])
  })

  it.each(['0-2；3', '4-2；3', '1-43；2', '1；；2', '1，；2', '1-2；三', '1-2；3/4'])(
    'still rejects invalid selection %s',
    (input) => expect(() => parseGroups(input, 42)).toThrow(),
  )
})
