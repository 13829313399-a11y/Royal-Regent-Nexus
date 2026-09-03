import { defineStore } from 'pinia'
import {
  approvalRows,
  departments,
  factoryContexts,
  isFactoryContextId,
  productionFactoryContextIds,
  type DepartmentId,
  type FactoryContextId,
  type ModuleDepartmentId,
  type ProductionFactoryContextId,
} from '@/data/enterpriseMock'

interface AuthenticatedFactoryContext {
  userId: string
  primaryFactoryId?: string | null
}

export const useAppStore = defineStore('app', {
  state: () => ({
    activeFactoryId: 'group' as FactoryContextId,
    authenticatedFactoryContext: null as AuthenticatedFactoryContext | null,
    requestedFactoryId: null as FactoryContextId | null,
    activeDepartmentId: 'engineering' as ModuleDepartmentId,
    selectedApprovalId: approvalRows[0]?.id ?? '',
    isRouteLoading: false,
  }),
  getters: {
    activeFactory(state) {
      return factoryContexts.find((factory) => factory.id === state.activeFactoryId) ?? factoryContexts[0]
    },
    activeProductionFactory(state) {
      const activeFactory = factoryContexts.find((factory) => factory.id === state.activeFactoryId)

      if (
        activeFactory
        && productionFactoryContextIds.includes(activeFactory.id as ProductionFactoryContextId)
      ) {
        return activeFactory
      }

      return factoryContexts.find((factory) => factory.id === 'huaxing') ?? factoryContexts[1]
    },
    activeDepartment(state) {
      return departments.find((department) => department.id === state.activeDepartmentId) ?? departments[0]
    },
    selectedApproval(state) {
      return approvalRows.find((approval) => approval.id === state.selectedApprovalId) ?? approvalRows[0]
    },
    departmentCount() {
      return departments.filter((department) => department.id !== 'overview').length
    },
  },
  actions: {
    // Record the destination without changing the visible context before authentication.
    // Session/profile updates also use this hint so a deep link stays authoritative.
    setRequestedFactoryContext(value: unknown) {
      const factoryId = Array.isArray(value) ? value[0] : value
      this.requestedFactoryId = typeof factoryId === 'string' && isFactoryContextId(factoryId)
        ? factoryId
        : null
    },
    syncAuthenticatedFactoryContext(context: AuthenticatedFactoryContext) {
      const primaryFactoryId = context.primaryFactoryId ?? null
      const previous = this.authenticatedFactoryContext
      const needsInitialization = !previous
        || previous.userId !== context.userId
        || previous.primaryFactoryId !== primaryFactoryId

      if (this.requestedFactoryId) {
        this.activeFactoryId = this.requestedFactoryId
      } else if (needsInitialization) {
        this.activeFactoryId = primaryFactoryId && isFactoryContextId(primaryFactoryId)
          ? primaryFactoryId
          : 'group'
      }

      if (needsInitialization) {
        this.authenticatedFactoryContext = { userId: context.userId, primaryFactoryId }
      }
    },
    resetAuthenticatedFactoryContext() {
      this.authenticatedFactoryContext = null
      this.requestedFactoryId = null
      this.activeFactoryId = 'group'
    },
    setActiveFactory(factoryId: FactoryContextId) {
      this.activeFactoryId = factoryId
    },
    setActiveDepartment(departmentId: ModuleDepartmentId) {
      this.activeDepartmentId = departmentId
    },
    selectApproval(approvalId: string) {
      this.selectedApprovalId = approvalId
    },
    startRouteLoading() {
      this.isRouteLoading = true
    },
    finishRouteLoading() {
      this.isRouteLoading = false
    },
  },
})
