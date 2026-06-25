<script setup lang="ts">
import { Check } from '@lucide/vue'
import { permissionRows } from '@/data/enterpriseMock'
import SectionPanel from '@/components/common/SectionPanel.vue'

const columns = [
  { key: 'view', label: '查看' },
  { key: 'edit', label: '编辑' },
  { key: 'approve', label: '审批' },
] as const
</script>

<template>
  <SectionPanel title="角色与权限矩阵" subtitle="模块级入口按厂区、部门、岗位控制">
    <div class="grid grid-cols-[1fr_repeat(3,56px)] items-center gap-y-4 text-sm">
      <span class="text-xs text-slate-500">角色</span>
      <span v-for="column in columns" :key="column.key" class="text-center text-xs text-slate-500">
        {{ column.label }}
      </span>

      <template v-for="row in permissionRows" :key="row.role">
        <span class="font-medium text-slate-800">{{ row.role }}</span>
        <span v-for="column in columns" :key="`${row.role}-${column.key}`" class="flex justify-center">
          <span
            class="flex size-5 items-center justify-center rounded"
            :class="row[column.key] ? 'bg-teal-700 text-white' : 'bg-slate-200 text-slate-400'"
          >
            <Check v-if="row[column.key]" class="size-3.5" aria-hidden="true" />
          </span>
        </span>
      </template>
    </div>
  </SectionPanel>
</template>
