<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { departments, getDepartmentRoute, isModuleDepartmentId, type ModuleDepartmentId } from '@/data/enterpriseMock'
import { Button } from '@/components/ui/button'
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
  router.push({
    path: getDepartmentRoute(departmentId),
    query: {
      ...route.query,
      factory: appStore.activeFactoryId,
    },
  })
}
</script>

<template>
  <div class="flex max-w-full gap-1 overflow-x-auto rounded-xl border border-slate-200/90 bg-white/85 p-1.5 shadow-[0_1px_2px_rgba(15,23,42,0.04)] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
    <Button
      v-for="department in departmentTabs"
      :key="department.id"
      type="button"
      size="lg"
      :variant="department.id === activeDepartmentId ? 'default' : 'ghost'"
      class="min-w-24"
      @click="selectDepartment(department.id as ModuleDepartmentId)"
    >
      {{ department.name }}
    </Button>
  </div>
</template>
