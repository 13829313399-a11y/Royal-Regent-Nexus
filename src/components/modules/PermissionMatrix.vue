<script setup lang="ts">
import { Check } from '@lucide/vue'
import type { PermissionRow } from '@/data/enterpriseMock'
import SectionPanel from '@/components/common/SectionPanel.vue'

withDefaults(defineProps<{
  rows: PermissionRow[]
  title?: string
  subtitle?: string
  /**
   * 外观变体。默认 `default` 保持原有样式与结构，
   * `portal` 只用于部门门户首页，`ModuleDetailView` 仍使用默认外观。
   */
  appearance?: 'default' | 'portal'
  /** 门户外观下的目录示意说明；默认外观不渲染。 */
  note?: string
}>(), {
  appearance: 'default',
  note: '',
})

const columns = [
  { key: 'view', label: '查看' },
  { key: 'edit', label: '编辑' },
  { key: 'approve', label: '审批' },
] as const
</script>

<template>
  <SectionPanel
    :class="appearance === 'portal' ? 'portal-section' : undefined"
    :title="title ?? '角色与权限矩阵'"
    :subtitle="subtitle ?? '模块级入口按厂区、部门、岗位控制'"
  >
    <template v-if="appearance === 'portal'">
      <div class="portal-matrix">
        <span class="portal-matrix__head">角色</span>
        <span v-for="column in columns" :key="column.key" class="portal-matrix__head text-center">
          {{ column.label }}
        </span>

        <template v-for="row in rows" :key="row.role">
          <span class="portal-matrix__role">{{ row.role }}</span>
          <span
            v-for="column in columns"
            :key="`${row.role}-${column.key}`"
            class="portal-matrix__cell"
          >
            <span
              class="portal-matrix__mark"
              :data-granted="row[column.key] ? 'true' : 'false'"
              :aria-label="`${row.role} ${column.label}${row[column.key] ? '有权限' : '无权限'}`"
            >
              <Check v-if="row[column.key]" class="size-3" aria-hidden="true" />
            </span>
          </span>
        </template>
      </div>
      <p v-if="note" class="portal-matrix__note">{{ note }}</p>
    </template>

    <div v-else class="grid grid-cols-[1fr_repeat(3,56px)] items-center text-sm">
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
