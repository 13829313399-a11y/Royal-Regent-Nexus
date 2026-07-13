<script setup lang="ts">
import { Check } from '@lucide/vue'
import type { PermissionRow } from '@/data/enterpriseMock'
import SectionPanel from '@/components/common/SectionPanel.vue'

defineProps<{
  rows: PermissionRow[]
  title?: string
  subtitle?: string
}>()

const columns = [
  { key: 'view', label: '查看' },
  { key: 'edit', label: '编辑' },
  { key: 'approve', label: '审批' },
] as const
</script>

<template>
  <SectionPanel :title="title ?? '角色与权限矩阵'" :subtitle="subtitle ?? '模块级入口按厂区、部门、岗位控制'">
    <div class="grid grid-cols-[1fr_repeat(3,56px)] items-center text-sm">
      <span class="pb-3 text-xs font-semibold text-slate-500">角色</span>
      <span v-for="column in columns" :key="column.key" class="pb-3 text-center text-xs font-semibold text-slate-500">
        {{ column.label }}
      </span>

      <template v-for="row in rows" :key="row.role">
        <span class="border-t border-slate-100 py-3 font-medium text-slate-800">{{ row.role }}</span>
        <span v-for="column in columns" :key="`${row.role}-${column.key}`" class="flex justify-center border-t border-slate-100 py-3">
          <span
            class="flex size-5 items-center justify-center rounded-md"
            :class="row[column.key] ? 'bg-teal-700 text-white shadow-sm' : 'bg-slate-100 text-slate-300 ring-1 ring-inset ring-slate-200'"
          >
            <Check v-if="row[column.key]" class="size-3.5" aria-hidden="true" />
          </span>
        </span>
      </template>
    </div>
  </SectionPanel>
</template>
