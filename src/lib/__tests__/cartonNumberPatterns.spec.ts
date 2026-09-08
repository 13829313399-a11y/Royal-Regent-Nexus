import { describe, expect, it } from 'vitest'
import { recognizeNumberTemplates, matchesNumberTemplate, parseNumberTemplate } from '../cartonNumberPatterns'

describe('frozen identifier templates', () => {
  it('merges only the observed alternative suffix widths', () => {
    expect(recognizeNumberTemplates(['SC700149169/600', 'SC700143393/1600', 'sc700149169/600'])).toEqual({ sampleCount: 2, templates: ['SC{9}/{3,4}'] })
    for (const value of ['SC700149169/600', 'sc700143393/1600']) expect(matchesNumberTemplate('SC{9}/{3,4}', value)).toBe(true)
    for (const value of ['SC700149169/60', 'SC700149169/60000', 'SC70014916/600', 'SX700149169/600', 'SC700149169/６００', 'SC700149169/600x']) expect(matchesNumberTemplate('SC{9}/{3,4}', value)).toBe(false)
    expect(matchesNumberTemplate('SC{9}/{3,5}', 'SC700149169/1600')).toBe(false)
  })
  it('does not invent cross-products when two numeric segments vary', () => {
    const result = recognizeNumberTemplates(['A12/300', 'A123/40'])
    expect(result.templates).toEqual(['A{2}/{3}', 'A{3}/{2}'])
    expect(result.templates.some(t => matchesNumberTemplate(t, 'A12/40'))).toBe(false)
  })
  it('handles one example, no evidence, literal separators and adjacent segments', () => {
    expect(recognizeNumberTemplates([]).templates).toEqual([])
    expect(recognizeNumberTemplates(['203307004']).templates).toEqual(['{9}'])
    expect(matchesNumberTemplate('A.{2}+{1}', 'A.12+3')).toBe(true)
    expect(matchesNumberTemplate('A.{2}+{1}', 'Ax12+3')).toBe(false)
    expect(matchesNumberTemplate('{1,2}{1,2}', '123')).toBe(true)
  })
  it.each(['', 'A{0}', 'A{3-4}', 'A{3,}', 'A{3', 'A{129}', 'A{128}', '{1,128}{1}', 'A {3}'])('rejects invalid or excessive template %s', template => {
    expect(() => parseNumberTemplate(template)).toThrow()
    expect(matchesNumberTemplate(template, 'A123')).toBe(false)
  })
})
