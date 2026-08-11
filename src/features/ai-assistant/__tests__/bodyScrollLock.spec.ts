import { afterEach, describe, expect, it } from 'vitest'
import { acquireBodyScrollLock } from '@/lib/bodyScrollLock'

afterEach(() => {
  document.body.style.overflow = ''
})

describe('shared body scroll lock', () => {
  it('keeps scrolling locked until every overlapping overlay releases its lock', () => {
    document.body.style.overflow = 'clip'

    const releaseNavigation = acquireBodyScrollLock()
    const releaseAssistant = acquireBodyScrollLock()
    expect(document.body.style.overflow).toBe('hidden')

    releaseNavigation()
    expect(document.body.style.overflow).toBe('hidden')

    releaseAssistant()
    expect(document.body.style.overflow).toBe('clip')

    releaseAssistant()
    expect(document.body.style.overflow).toBe('clip')
  })
})
