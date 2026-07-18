import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AuthAmbientGrid from '../AuthAmbientGrid.vue'

const source = readFileSync(
  join(process.cwd(), 'src/components/auth/AuthAmbientGrid.vue'),
  'utf8',
)

describe('AuthAmbientGrid', () => {
  it.each([
    { variant: 'login' as const, candidateCount: 9 },
    { variant: 'register' as const, candidateCount: 6 },
  ])('renders the fixed $variant decoration safely', ({ variant, candidateCount }) => {
    const wrapper = mount(AuthAmbientGrid, { props: { variant } })
    const root = wrapper.get('.auth-ambient-grid')
    const cells = wrapper.findAll('.auth-ambient-grid__cell')

    expect(root.attributes('aria-hidden')).toBe('true')
    expect(root.attributes('data-variant')).toBe(variant)
    expect(Number(root.attributes('data-candidate-count'))).toBe(candidateCount)
    expect(cells).toHaveLength(candidateCount)
    expect(candidateCount).toBeLessThanOrEqual(variant === 'login' ? 10 : 7)
    expect(candidateCount).toBeGreaterThanOrEqual(variant === 'login' ? 8 : 5)
    expect(wrapper.find('a, button, input, select, textarea, [tabindex]').exists()).toBe(false)
    expect(cells.every((cell) => cell.attributes('aria-hidden') === 'true')).toBe(true)
  })

  it('uses deterministic, bounded CSS animation configuration', () => {
    for (const variant of ['login', 'register'] as const) {
      const firstRender = mount(AuthAmbientGrid, { props: { variant } })
      const secondRender = mount(AuthAmbientGrid, { props: { variant } })
      const firstStyles = firstRender.findAll('.auth-ambient-grid__cell').map((cell) => cell.attributes('style'))
      const secondStyles = secondRender.findAll('.auth-ambient-grid__cell').map((cell) => cell.attributes('style'))

      expect(firstStyles).toEqual(secondStyles)
      expect(new Set(firstStyles).size).toBe(firstStyles.length)

      const durations = new Set<number>()
      for (const style of firstStyles) {
        const duration = Number(style.match(/--ambient-duration:\s*([\d.]+)s/)?.[1])
        durations.add(duration)
        expect(duration).toBeGreaterThanOrEqual(14)
        expect(duration).toBeLessThanOrEqual(22)
        expect(style).toMatch(/--ambient-grid-column:\s*-?\d+/)
        expect(style).toMatch(/--ambient-grid-row:\s*-?\d+/)
      }
      expect(durations.size).toBe(1)

      const animationWindow = 0.14
      const duration = [...durations][0] ?? 0
      let maximumVisibleCells = 0

      for (let time = 0; time < duration; time += 0.05) {
        const visibleCells = firstStyles.filter((style) => {
          const delay = Number(style.match(/--ambient-delay:\s*(-?[\d.]+)s/)?.[1])
          const phase = (((time - delay) % duration) + duration) % duration / duration
          return phase > 0 && phase < animationWindow
        }).length
        maximumVisibleCells = Math.max(maximumVisibleCells, visibleCells)
      }

      expect(maximumVisibleCells).toBeLessThanOrEqual(3)
    }

    expect(source).not.toContain('Math.random')
    expect(source).not.toContain('setInterval')
    expect(source).not.toContain('requestAnimationFrame')
    expect(source).not.toMatch(/<canvas\b/i)
    expect(source).not.toMatch(/mouse(move|enter|leave)|pointer(move|enter|leave)/i)
  })

  it('fully stops looping motion for reduced-motion users', () => {
    const reducedMotionStart = source.indexOf('@media (prefers-reduced-motion: reduce)')
    expect(reducedMotionStart).toBeGreaterThan(-1)

    const reducedMotionSource = source.slice(reducedMotionStart)
    expect(reducedMotionSource).toMatch(/\.auth-ambient-grid__cell\s*\{[\s\S]*?animation:\s*none\s*!important/)
    expect(source).toMatch(/pointer-events:\s*none;/)
    expect(source).toContain('--ambient-grid-size: 46px')
    expect(source).toContain('--ambient-grid-size: 42px')
    expect(source).toContain('grid-template-columns: repeat(auto-fill, var(--ambient-grid-size))')
    expect(source).toMatch(/@media \(max-height: 940px\)[\s\S]*?login-lower-inner-east[\s\S]*?animation:\s*none;/)
    expect(source).not.toContain('auth-ambient-grid__cursor')
  })
})
