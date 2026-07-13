<script setup lang="ts">
import type { TodoItem } from '@/data/enterpriseMock'
import SectionPanel from '@/components/common/SectionPanel.vue'

defineProps<{
  items: TodoItem[]
  title?: string
  subtitle?: string
}>()
</script>

<template>
  <SectionPanel :title="title ?? '部门待办队列'" :subtitle="subtitle ?? '聚合该部门所有模块的事项'">
    <div class="space-y-3">
      <article
        v-for="(todo, index) in items"
        :key="todo.id"
        class="surface-subtle flex gap-3 rounded-xl px-4 py-3"
      >
        <span class="flex size-6 shrink-0 items-center justify-center rounded-md bg-white text-[11px] font-bold text-teal-700 shadow-sm ring-1 ring-inset ring-teal-100">
          {{ index + 1 }}
        </span>
        <div class="min-w-0">
          <h3 class="font-semibold text-slate-950">{{ todo.id }} {{ todo.title }}</h3>
          <p class="mt-1 text-xs leading-5 text-slate-500">{{ todo.meta }}</p>
        </div>
      </article>
    </div>
  </SectionPanel>
</template>
