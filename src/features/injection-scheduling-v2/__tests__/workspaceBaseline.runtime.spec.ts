import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import InjectionSchedulingV2View from '../InjectionSchedulingV2View.vue'
import { createBusinessSchedulingBaselineFixture } from './fixtures/schedulingBaselineFixture'
import { seedSchedulingBaselineStore } from './helpers/seedSchedulingBaselineStore'

class BaselineResizeObserver implements ResizeObserver {
  constructor(private readonly callback: ResizeObserverCallback) {}

  observe(target: Element) {
    this.callback([{
      target,
      contentRect: { x: 0, y: 0, width: 1_200, height: 420, top: 0, right: 1_200, bottom: 420, left: 0, toJSON: () => ({}) },
      borderBoxSize: [],
      contentBoxSize: [],
      devicePixelContentBoxSize: [],
    }], this)
  }

  unobserve() {}
  disconnect() {}
}

function p95(samples: number[]) {
  const sorted = [...samples].sort((left, right) => left - right)
  return sorted[Math.max(0, Math.ceil(sorted.length * 0.95) - 1)] ?? 0
}

describe('InjectionSchedulingV2View B0 workspace + store baseline', () => {
  beforeEach(() => {
    vi.stubGlobal('ResizeObserver', BaselineResizeObserver)
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      callback(0)
      return 1
    })
    vi.stubGlobal('cancelAnimationFrame', () => undefined)
    Object.defineProperty(HTMLElement.prototype, 'clientHeight', {
      configurable: true,
      get() { return this.classList.contains('machine-plan-scroll') ? 420 : 0 },
    })
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
      configurable: true,
      get() { return this.classList.contains('machine-plan-scroll') ? 1_200 : 0 },
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  it('mounts the complete workspace against the 76 machine / 1500 task in-memory fixture', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = seedSchedulingBaselineStore(pinia, createBusinessSchedulingBaselineFixture())
    store.load = vi.fn(async () => undefined)
    store.pollEvents = vi.fn(async () => undefined)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/modules/production/injection-scheduling', name: 'injection-scheduling', component: { template: '<div />' } },
        { path: '/', name: 'dashboard', component: { template: '<div />' } },
        { path: '/molds', name: 'injection-scheduling-mold-database', component: { template: '<div />' } },
        { path: '/machines', name: 'injection-scheduling-machine-database', component: { template: '<div />' } },
      ],
    })
    await router.push('/modules/production/injection-scheduling?factory=huaxing')
    await router.isReady()

    const mountStartedAt = performance.now()
    const wrapper = mount(InjectionSchedulingV2View, {
      attachTo: document.body,
      global: { plugins: [pinia, router] },
    })
    await nextTick()
    await nextTick()
    const workspaceMountMs = performance.now() - mountStartedAt

    expect(store.load).toHaveBeenCalledTimes(1)
    expect(store.machines).toHaveLength(76)
    expect(store.tasks).toHaveLength(1_500)
    expect(store.gridRows).toHaveLength(1_576)
    expect(store.visibleColumns).toHaveLength(16)
    expect(wrapper.find('[aria-label="排产命令栏"]').exists()).toBe(true)
    expect(wrapper.get('[aria-label="排产关键指标"]').text()).toContain('76')
    expect(wrapper.find('[data-testid="machine-plan-virtual-scroll"]').exists()).toBe(true)
    expect(wrapper.findAll('.column-title-row th')).toHaveLength(16)
    expect(store.sourceMessage).toBe('B0 去敏基线 fixture')
    expect(wrapper.text()).toContain('只读演示')
    expect(wrapper.text()).not.toContain('FFD442')

    for (let index = 0; index < 3; index += 1) {
      store.search = index % 2 === 0 ? 'QA-ORDER-00001' : ''
      await nextTick()
    }
    const searchSamples: number[] = []
    for (let index = 0; index < 20; index += 1) {
      const startedAt = performance.now()
      store.search = index % 2 === 0 ? 'QA-ORDER-00001' : ''
      await nextTick()
      searchSamples.push(performance.now() - startedAt)
    }
    store.search = ''
    await nextTick()

    const presetSamples: number[] = []
    for (let index = 0; index < 20; index += 1) {
      const startedAt = performance.now()
      store.setPreset(index % 2 === 0 ? 'full' : 'planner')
      await nextTick()
      presetSamples.push(performance.now() - startedAt)
    }
    store.setPreset('full')
    await nextTick()
    expect(store.visibleColumns).toHaveLength(50)
    expect(wrapper.findAll('.column-title-row th')).toHaveLength(50)

    const measurement = {
      fixtureVersion: 'b0-v1',
      containsProductionData: false,
      timingContext: 'Vitest jsdom full Workspace + Store comparison evidence, not a browser SLA',
      machines: store.machines.length,
      tasks: store.tasks.length,
      workspaceMountMs: Number(workspaceMountMs.toFixed(3)),
      searchP95Ms: Number(p95(searchSamples).toFixed(3)),
      presetSwitchP95Ms: Number(p95(presetSamples).toFixed(3)),
    }
    expect(measurement).toMatchObject({ machines: 76, tasks: 1_500 })
    expect(Number.isFinite(measurement.workspaceMountMs)).toBe(true)
    expect(Number.isFinite(measurement.searchP95Ms)).toBe(true)
    expect(Number.isFinite(measurement.presetSwitchP95Ms)).toBe(true)
    console.info(`B2A_WORKSPACE ${JSON.stringify(measurement)}`)

    wrapper.unmount()
  }, 30_000)
})
