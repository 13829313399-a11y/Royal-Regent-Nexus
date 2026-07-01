import { defineStore } from 'pinia'
import {
  approvalRows,
  departments,
  factoryContexts,
  type DepartmentId,
  type FactoryContextId,
  type ModuleDepartmentId,
} from '@/data/enterpriseMock'

export const useAppStore = defineStore('app', {
  state: () => ({
    activeFactoryId: 'group' as FactoryContextId,
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

      if (activeFactory && activeFactory.id !== 'group') {
        return activeFactory
      }

      return factoryContexts.find((factory) => factory.id === 'huakang-a') ?? factoryContexts[1]
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
