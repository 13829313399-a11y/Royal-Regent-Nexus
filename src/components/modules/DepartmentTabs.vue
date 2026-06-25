<script setup lang="ts">
import { departments, type DepartmentId } from '@/data/enterpriseMock'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()

const departmentTabs = departments.filter((department) => department.id !== 'overview')

function selectDepartment(departmentId: DepartmentId) {
  appStore.setActiveDepartment(departmentId)
}
</script>

<template>
  <div class="flex flex-wrap gap-3">
    <button
      v-for="department in departmentTabs"
      :key="department.id"
      type="button"
      class="h-10 min-w-24 rounded-lg border px-5 text-sm font-semibold transition-colors"
      :class="department.id === appStore.activeDepartmentId
        ? 'border-teal-700 bg-teal-700 text-white'
        : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'"
      @click="selectDepartment(department.id)"
    >
      {{ department.name }}
    </button>
  </div>
</template>
