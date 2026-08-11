import { createApp } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import InjectionSchedulingV2View from '../../InjectionSchedulingV2View.vue'
import { createBusinessSchedulingBaselineFixture } from '../fixtures/schedulingBaselineFixture'
import { seedSchedulingBaselineStore } from '../helpers/seedSchedulingBaselineStore'

const pinia = createPinia()
setActivePinia(pinia)
const fixture = createBusinessSchedulingBaselineFixture()
const store = seedSchedulingBaselineStore(pinia, fixture)
store.load = async () => undefined
store.pollEvents = async () => undefined

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/src/features/injection-scheduling-v2/__tests__/harness/b0-baseline.html', name: 'injection-scheduling', component: InjectionSchedulingV2View },
    { path: '/', name: 'dashboard', component: { template: '<div />' } },
    { path: '/molds', name: 'injection-scheduling-mold-database', component: { template: '<div />' } },
    { path: '/machines', name: 'injection-scheduling-machine-database', component: { template: '<div />' } },
  ],
})

await router.push('/src/features/injection-scheduling-v2/__tests__/harness/b0-baseline.html?factory=huaxing')
await router.isReady()

const app = createApp(InjectionSchedulingV2View)
app.use(pinia)
app.use(router)
app.mount('#app')

document.documentElement.dataset.fixtureVersion = fixture.metadata.fixtureVersion
document.documentElement.dataset.fixtureMachines = String(fixture.metadata.machineCount)
document.documentElement.dataset.fixtureTasks = String(fixture.metadata.taskCount)
document.documentElement.dataset.containsProductionData = String(fixture.metadata.containsProductionData)
document.documentElement.dataset.browserUserAgent = navigator.userAgent
document.documentElement.dataset.devicePixelRatio = String(window.devicePixelRatio)
document.documentElement.dataset.longTaskSupported = String(PerformanceObserver.supportedEntryTypes.includes('longtask'))
document.documentElement.dataset.longTaskCount = '0'
document.documentElement.dataset.longTaskMaxDurationMs = '0'
document.documentElement.dataset.longTaskDurationsMs = '[]'
document.documentElement.dataset.searchSampleCount = '0'
document.documentElement.dataset.searchP95Ms = '0'
document.documentElement.dataset.searchMaxMs = '0'
document.documentElement.dataset.visibleGridRows = String(document.querySelectorAll('.machine-plan-table tbody tr').length)

const searchLatencySamples: number[] = []
const workspaceSearch = document.querySelector<HTMLInputElement>('input[placeholder="机号 / 工模 / 产品 / 单号 / 货号"]')
workspaceSearch?.addEventListener('input', () => {
  const startedAt = performance.now()
  requestAnimationFrame(() => requestAnimationFrame(() => {
    searchLatencySamples.push(performance.now() - startedAt)
    const sorted = [...searchLatencySamples].sort((left, right) => left - right)
    const p95Index = Math.max(0, Math.ceil(sorted.length * 0.95) - 1)
    document.documentElement.dataset.searchSampleCount = String(searchLatencySamples.length)
    document.documentElement.dataset.searchP95Ms = String(Number((sorted[p95Index] ?? 0).toFixed(3)))
    document.documentElement.dataset.searchMaxMs = String(Number(Math.max(...searchLatencySamples).toFixed(3)))
    document.documentElement.dataset.visibleGridRows = String(document.querySelectorAll('.machine-plan-table tbody tr').length)
  }))
})

if (PerformanceObserver.supportedEntryTypes.includes('longtask')) {
  let longTaskCount = 0
  let longTaskMaxDurationMs = 0
  const longTaskDurationsMs: number[] = []
  const observer = new PerformanceObserver((list) => {
    for (const entry of list.getEntries()) {
      longTaskCount += 1
      longTaskMaxDurationMs = Math.max(longTaskMaxDurationMs, entry.duration)
      longTaskDurationsMs.push(Number(entry.duration.toFixed(3)))
    }
    document.documentElement.dataset.longTaskCount = String(longTaskCount)
    document.documentElement.dataset.longTaskMaxDurationMs = String(longTaskMaxDurationMs)
    document.documentElement.dataset.longTaskDurationsMs = JSON.stringify(longTaskDurationsMs.slice(-50))
  })
  observer.observe({ entryTypes: ['longtask'] })
}

document.documentElement.dataset.baselineReady = 'true'
