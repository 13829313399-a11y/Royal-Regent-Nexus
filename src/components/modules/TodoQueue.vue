<script setup lang="ts">
import type { TodoItem } from '@/data/enterpriseMock'
import SectionPanel from '@/components/common/SectionPanel.vue'

withDefaults(defineProps<{
  items: TodoItem[]
  title?: string
  subtitle?: string
  /**
   * 外观变体。默认 `default` 保持原有样式，`portal` 只用于部门门户首页。
   */
  appearance?: 'default' | 'portal'
  /** 门户外观下的紧凑空态文案；没有本厂待办时使用。 */
  emptyText?: string
}>(), {
  appearance: 'default',
  emptyText: '当前暂无可展示的本厂待办',
})
</script>

<template>
  <SectionPanel
    :class="appearance === 'portal' ? 'portal-section' : undefined"
    :title="title ?? '部门待办队列'"
    :subtitle="subtitle ?? '聚合该部门所有模块的事项'"
  >
    <template v-if="appearance === 'portal'">
      <p v-if="!items.length" class="portal-todo__empty">{{ emptyText }}</p>
      <div v-else>
        <article
          v-for="(todo, index) in items"
          :key="todo.id"
          class="portal-todo"
        >
          <span class="portal-todo__index" aria-hidden="true">{{ index + 1 }}</span>
          <div class="min-w-0">
            <h3 class="portal-todo__title">{{ todo.id }} {{ todo.title }}</h3>
            <p class="portal-todo__meta">{{ todo.meta }}</p>
          </div>
        </article>
      </div>
    </template>

    <div v-else class="space-y-3">
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
