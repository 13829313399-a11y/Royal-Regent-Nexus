import { describe, expect, it } from 'vitest'
import { cartonDimensionParts, formatCartonSpecification } from '../cartonDimensions'

describe('carton dimension display', () => {
  it('defaults an unmarked legacy size to cm, leaving empty sizes empty', () => {
    expect(formatCartonSpecification('12*11*5')).toBe('12*11*5 cm')
    expect(formatCartonSpecification('')).toBe('')
  })
  it('preserves explicit units without duplicating receipt inventory suffixes', () => {
    expect(formatCartonSpecification('12*11*5 in')).toBe('12*11*5 in')
    expect(formatCartonSpecification('12*11*5 [in]')).toBe('12*11*5 in')
    expect(formatCartonSpecification('12*11*5', 'in')).toBe('12*11*5 in')
    expect(cartonDimensionParts('12*11*5 [in]')).toEqual({ specification: '12*11*5', unit: 'in' })
  })
  it.each([['″', 'in'], ['"', 'in'], ['公分', 'cm'], ['ft', 'ft'], ['m', 'm'], ['毫米', 'mm']])('preserves legacy %s suffixes', (suffix, unit) => {
    expect(formatCartonSpecification(`12*11*5 ${suffix}`, null)).toBe(`12*11*5 ${unit}`)
    expect(formatCartonSpecification(`12*11*5 ${suffix}`, unit)).toBe(`12*11*5 ${unit}`)
  })
  it('does not truncate words ending in unit letters', () => {
    expect(cartonDimensionParts('thin')).toEqual({ specification: 'thin', unit: 'cm' })
    expect(formatCartonSpecification('12*11*5', 'inch')).toBe('12*11*5 in')
  })
  it('recognizes separated and bracketed units after text without hiding earlier unit markers', () => {
    expect(cartonDimensionParts('foam [in]')).toEqual({ specification: 'foam', unit: 'in' })
    expect(cartonDimensionParts('foam in')).toEqual({ specification: 'foam', unit: 'in' })
    expect(cartonDimensionParts('12*10*5 mm [cm]')).toEqual({ specification: '12*10*5 mm', unit: 'cm' })
    expect(cartonDimensionParts('12*10*5mm[cm]')).toEqual({ specification: '12*10*5mm', unit: 'cm' })
  })
})
