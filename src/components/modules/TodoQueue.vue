<script setup lang="ts">
import { departmentTodos } from '@/data/enterpriseMock'
import SectionPanel from '@/components/common/SectionPanel.vue'
</script>

<template>
  <SectionPanel title="部门待办队列" subtitle="聚合该部门所有模块的事项">
    <div class="space-y-3">
      <article
        v-for="todo in departmentTodos"
        :key="todo.id"
        class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3"
      >
        <h3 class="font-semibold text-slate-950">{{ todo.id }} {{ todo.title }}</h3>
        <p class="mt-1 text-xs text-slate-500">{{ todo.meta }}</p>
      </article>
    </div>
  </SectionPanel>
</template>
