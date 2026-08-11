import type { Pinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { useInjectionSchedulingV2Store } from '../../stores/useInjectionSchedulingV2Store'
import type { SchedulingBaselineFixture } from '../fixtures/schedulingBaselineFixture'

const baselinePermissions = [
  'injection_scheduling:edit',
  'injection_scheduling:report',
  'injection_scheduling:publish',
  'injection_scheduling:import',
  'injection_scheduling:export',
]

export function seedSchedulingBaselineStore(pinia: Pinia, fixture: SchedulingBaselineFixture) {
  const authStore = useAuthStore(pinia)
  authStore.permissions = [...baselinePermissions]
  authStore.factoryScopes = ['huaxing']
  authStore.isAuthenticated = true
  authStore.hasLoadedSession = true

  const store = useInjectionSchedulingV2Store(pinia)
  const executionSlice = {
    plan: fixture.plan,
    orders: fixture.orders,
    tasks: fixture.tasks,
    selectedTaskId: null,
    search: '',
    statusFilter: 'all',
    riskFilter: 'all',
    cellDrafts: {},
    timelineScrollLeft: 0,
    timelineZoom: 1,
  }
  const emptyPlanningSlice = {
    plan: null,
    orders: [],
    tasks: [],
    selectedTaskId: null,
    search: '',
    statusFilter: 'all',
    riskFilter: 'all',
    cellDrafts: {},
    timelineScrollLeft: 0,
    timelineZoom: 1,
  }

  store.machines = fixture.machines
  store.molds = fixture.molds
  store.orders = fixture.orders
  store.tasks = fixture.tasks
  store.plan = fixture.plan
  store.executionPlan = fixture.plan
  store.planningPlan = null
  store.executionPublishedPlan = executionSlice
  store.planningDraftPlan = emptyPlanningSlice
  store.activePlanSlice = 'execution'
  store.sourceMode = 'fallback'
  store.sourceMessage = 'B0 去敏基线 fixture'
  store.syncHealth = 'demo-readonly'
  store.syncFailureKind = null
  store.hasFormalSnapshot = false
  store.lastSyncedAt = '10:00'
  store.pollingRevision = 98
  store.activePreset = 'planner'
  store.activeView = 'plan'
  store.selectedTaskId = null
  store.backlogDockOpen = false
  store.collapsedMachineIds = []
  store.customVisibleColumns = {}
  store.columnWidths = {}
  store.sort = null
  store.cellDrafts = {}

  return store
}
