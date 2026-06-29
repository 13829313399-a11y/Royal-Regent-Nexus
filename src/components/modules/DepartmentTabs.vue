<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { departments, getDepartmentRoute, isModuleDepartmentId, type ModuleDepartmentId } from '@/data/enterpriseMock'
import { useAppStore } from '@/stores/app'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()

const departmentTabs = departments.filter((department) => department.id !== 'overview')
const activeDepartmentId = computed<ModuleDepartmentId>(() => {
  const routeDepartment = String(route.params.department ?? '')
  return isModuleDepartmentId(routeDepartment) ? routeDepartment : appStore.activeDepartmentId
})

function selectDepartment(departmentId: ModuleDepartmentId) {
  appStore.setActiveDepartment(departmentId)
  router.push(getDepartmentRoute(departmentId))
}
</script>

<template>
  <div class="flex flex-wrap gap-3">
    <button
      v-for="department in departmentTabs"
      :key="department.id"
      type="button"
      class="h-10 min-w-24 rounded-lg border px-5 text-sm font-semibold transition-colors"
      :class="department.id === activeDepartmentId
        ? 'border-teal-700 bg-teal-700 text-white'
        : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'"
      @click="selectDepartment(department.id as ModuleDepartmentId)"
    >
      {{ department.name }}
    </button>
  </div>
</template>
