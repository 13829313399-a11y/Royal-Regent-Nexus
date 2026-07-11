<script setup lang="ts">
import { Building2, Factory } from '@lucide/vue'
import type { ManageableScope } from '@/api/iam'

const props = defineProps<{
  scopes: ManageableScope[]
  factoryId: string
  department: string
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:factoryId': [value: string]
  'update:department': [value: string]
}>()

function selectFactory(value: string) {
  emit('update:factoryId', value)
  const firstDepartment = props.scopes.find((scope) => scope.factory_id === value)?.department ?? '*'
  emit('update:department', firstDepartment)
}
</script>

<template>
  <section class="min-w-0 max-w-full rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
    <div class="mb-4">
      <h2 class="font-bold text-slate-950">调整作用范围</h2>
      <p class="mt-1 text-sm text-slate-500">权限矩阵只显示并修改当前厂区与部门范围，不会串联其他授权。</p>
    </div>
    <div class="grid gap-4 md:grid-cols-2">
      <label class="grid gap-1.5 text-sm font-semibold text-slate-700">
        <span class="flex items-center gap-2"><Factory class="size-4 text-emerald-700" />厂区</span>
        <select
          :value="factoryId"
          :disabled="disabled"
          class="h-11 w-full min-w-0 rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100 disabled:bg-slate-100"
          @change="selectFactory(($event.target as HTMLSelectElement).value)"
        >
          <option v-for="scope in scopes.filter((item, index, values) => values.findIndex((candidate) => candidate.factory_id === item.factory_id) === index)" :key="scope.factory_id" :value="scope.factory_id">
            {{ scope.factory_name || scope.factory_id }}
          </option>
        </select>
      </label>
      <label class="grid gap-1.5 text-sm font-semibold text-slate-700">
        <span class="flex items-center gap-2"><Building2 class="size-4 text-emerald-700" />部门</span>
        <select
          :value="department"
          :disabled="disabled"
          class="h-11 w-full min-w-0 rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100 disabled:bg-slate-100"
          @change="emit('update:department', ($event.target as HTMLSelectElement).value)"
        >
          <option v-for="scope in scopes.filter((item) => item.factory_id === factoryId)" :key="`${scope.factory_id}:${scope.department}`" :value="scope.department">
            {{ scope.department_name || scope.department }}
          </option>
        </select>
      </label>
    </div>
  </section>
</template>
