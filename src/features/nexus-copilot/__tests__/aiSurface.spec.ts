import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AiEdgeHandle from '../surfaces/AiEdgeHandle.vue'
import AiSurfaceWindow from '../surfaces/AiSurfaceWindow.vue'
import { useAISurfaceStore } from '../surfaces/surfaceStore'
import { clampSurfaceGeometry } from '../surfaces/useWindowGeometry'

describe('adaptive AI surface', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1280 })
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 800 })
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
    })
  })

  it('stores only bounded versioned UI geometry and restores the preferred mode', () => {
    const store = useAISurfaceStore()
    store.hydrate()
    store.setGeometry({ x: 4_000, y: -100, width: 2_000, height: 2_000 })
    store.setMode('DOCKED_LEFT')
    store.minimize()
    const saved = JSON.parse(localStorage.getItem('rr:nexus-ai-surface:v1') ?? '{}')
    expect(Object.keys(saved).sort()).toEqual(['dockWidth', 'edgeY', 'geometry', 'lastDesktopMode', 'mode', 'version'])
    expect(JSON.stringify(saved)).not.toMatch(/message|prompt|tool|evidence|token|secret/i)
    expect(saved.geometry.x + saved.geometry.width).toBeLessThanOrEqual(window.innerWidth)
    store.open()
    expect(store.mode).toBe('DOCKED_LEFT')
  })

  it('preserves the desktop dock preference while the surface is mobile fullscreen', () => {
    const desktopStore = useAISurfaceStore()
    desktopStore.hydrate()
    desktopStore.setDockWidth(500)
    desktopStore.setMode('DOCKED_RIGHT')

    setActivePinia(createPinia())
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 390 })
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn().mockReturnValue({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
    })
    const mobileStore = useAISurfaceStore()
    mobileStore.hydrate()
    mobileStore.open()

    expect(mobileStore.dockWidth).toBe(500)
    expect(mobileStore.mode).toBe('FULLSCREEN_MOBILE')
  })

  it('clamps floating geometry inside the viewport', () => {
    expect(clampSurfaceGeometry({ x: -20, y: 900, width: 100, height: 2_000 })).toMatchObject({
      x: 8,
      width: 360,
      height: 736,
    })
  })

  it('renders a 40px edge handle and supports open plus vertical movement', async () => {
    const wrapper = mount(AiEdgeHandle, { props: { side: 'right', y: 120 } })
    expect(wrapper.classes()).toContain('w-10')
    await wrapper.trigger('click')
    expect(wrapper.emitted('open')).toHaveLength(1)
  })

  it('uses non-modal semantics on desktop and modal semantics only on mobile', async () => {
    const wrapper = mount(AiSurfaceWindow, {
      props: {
        mode: 'FLOATING',
        geometry: { x: 20, y: 20, width: 440, height: 640 },
        dockWidth: 440,
        closeLabel: '关闭 AI 助手',
      },
      slots: { identity: '<span>AI</span>', default: '<button>业务内容</button>' },
    })
    expect(wrapper.attributes('role')).toBe('complementary')
    expect(wrapper.attributes('aria-modal')).toBeUndefined()
    await wrapper.setProps({ mode: 'FULLSCREEN_MOBILE' })
    expect(wrapper.attributes('role')).toBe('dialog')
    expect(wrapper.attributes('aria-modal')).toBe('true')
  })

  it('provides keyboard movement and dock controls', async () => {
    const wrapper = mount(AiSurfaceWindow, {
      props: {
        mode: 'FLOATING',
        geometry: { x: 20, y: 20, width: 440, height: 640 },
        dockWidth: 440,
        closeLabel: '关闭 AI 助手',
      },
    })
    await wrapper.get('header').trigger('keydown', { key: 'ArrowRight', altKey: true })
    expect(wrapper.emitted('geometry')?.at(-1)?.[0]).toMatchObject({ x: 32 })
    await wrapper.get('button[aria-label="停靠到左侧"]').trigger('click')
    expect(wrapper.emitted('mode')?.at(-1)).toEqual(['DOCKED_LEFT'])

    await wrapper.setProps({ mode: 'DOCKED_RIGHT' })
    const separator = wrapper.get('[role="separator"][aria-label="调整停靠面板宽度"]')
    expect(separator.attributes('aria-valuenow')).toBe('440')
    await separator.trigger('keydown', { key: 'ArrowLeft' })
    expect(wrapper.emitted('dockWidth')?.at(-1)).toEqual([456, true])
  })
})
